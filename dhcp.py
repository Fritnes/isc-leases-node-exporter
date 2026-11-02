#!/usr/bin/env python3
import argparse
import bisect
import datetime
import os
import sys
import tempfile
import time

def parse_timestamp(raw_str):
        tokens = raw_str.split()
        if len(tokens) == 1:
                if tokens[0].lower() == 'never':
                        return 'never';
                else:
                        raise Exception('Parse error in timestamp')
        elif len(tokens) == 3:
                return datetime.datetime.strptime(' '.join(tokens[1:]),
                        '%Y/%m/%d %H:%M:%S')
        else:
                raise Exception('Parse error in timestamp')

def timestamp_is_ge(t1, t2):
        if t1 == 'never':
                return True
        elif t2 == 'never':
                return False
        else:
                return t1 >= t2

def timestamp_is_lt(t1, t2):
        if t1 == 'never':
                return False
        elif t2 == 'never':
                return t1 != 'never'
        else:
                return t1 < t2

def timestamp_is_between(t, tstart, tend):
        return timestamp_is_ge(t, tstart) and timestamp_is_lt(t, tend)

def parse_hardware(raw_str):
        tokens = raw_str.split()
        if len(tokens) == 2:
                return tokens[1]
        else:
                raise Exception('Parse error in hardware')

def strip_endquotes(raw_str):
        return raw_str.strip('"')

def identity(raw_str):
        return raw_str

def parse_binding_state(raw_str):
        tokens = raw_str.split()
        if len(tokens) == 2:
                return tokens[1]
        else:
                raise Exception('Parse error in binding state')

def parse_next_binding_state(raw_str):
        tokens = raw_str.split()
        if len(tokens) == 3:
                return tokens[2]
        else:
                raise Exception('Parse error in next binding state')

def parse_rewind_binding_state(raw_str):
        tokens = raw_str.split()
        if len(tokens) == 3:
                return tokens[2]
        else:
                raise Exception('Parse error in next binding state')

def parse_leases_file(leases_file):
        valid_keys = {
                'starts':               parse_timestamp,
                'ends':                 parse_timestamp,
                'tstp':                 parse_timestamp,
                'tsfp':                 parse_timestamp,
                'atsfp':                parse_timestamp,
                'cltt':                 parse_timestamp,
                'hardware':             parse_hardware,
                'binding':              parse_binding_state,
                'next':                 parse_next_binding_state,
                'rewind':               parse_rewind_binding_state,
                'uid':                  strip_endquotes,
                'client-hostname':      strip_endquotes,
                'option':               identity,
                'set':                  identity,
                'on':                   identity,
                'abandoned':            None,
                'bootp':                None,
                'reserved':             None,
                }

        leases_db = {}
        lease_rec = {}
        in_lease = False
        in_failover = False
        for line in leases_file:
                if line.lstrip().startswith('#'):
                        continue
                tokens = line.split()
                if len(tokens) == 0:
                        continue
                key = tokens[0].lower()
                if key == 'lease':
                        if not in_lease:
                                ip_address = tokens[1]
                                lease_rec = {'ip_address' : ip_address}
                                in_lease = True
                        else:
                                raise Exception('Parse error in leases file')

                elif key == 'failover':
                        in_failover = True
                elif key == '}':
                        if in_lease:
                                for k in valid_keys:
                                        if callable(valid_keys[k]):
                                                lease_rec[k] = lease_rec.get(k, '')
                                        else:
                                                lease_rec[k] = False
                                ip_address = lease_rec['ip_address']
                                if ip_address in leases_db:
                                        leases_db[ip_address].insert(0, lease_rec)
                                else:
                                        leases_db[ip_address] = [lease_rec]
                                lease_rec = {}
                                in_lease = False
                        elif in_failover:
                                in_failover = False
                                continue
                        else:
                                raise Exception('Parse error in leases file')
                elif key in valid_keys:
                        if in_lease:
                                value = line[(line.index(key) + len(key)):]
                                value = value.strip().rstrip(';').rstrip()
                                if callable(valid_keys[key]):
                                        lease_rec[key] = valid_keys[key](value)
                                else:
                                        lease_rec[key] = True
                        else:
                                raise Exception('Parse error in leases file')
                else:
                        if in_lease:
                                raise Exception('Parse error in leases file')
        if in_lease:
                raise Exception('Parse error in leases file')
        return leases_db

def round_timedelta(tdelta):
        return datetime.timedelta(tdelta.days,
                tdelta.seconds + (0 if tdelta.microseconds < 500000 else 1))

def timestamp_now():
        n = datetime.datetime.now(datetime.timezone.utc)
        if n.microsecond >= 500000:
                n += datetime.timedelta(seconds=1)
        return n.replace(microsecond=0, tzinfo=None)

def lease_is_active(lease_rec, as_of_ts):
        return timestamp_is_between(as_of_ts, lease_rec['starts'],
                lease_rec['ends'])

def ipv4_to_int(ipv4_addr):
        parts = ipv4_addr.split('.')
        return (int(parts[0]) << 24) + (int(parts[1]) << 16) + \
                (int(parts[2]) << 8) + int(parts[3])

def select_active_leases(leases_db, as_of_ts):
        retarray = []
        sortedarray = []
        for ip_address in leases_db:
                lease_rec = leases_db[ip_address][0]
                if lease_is_active(lease_rec, as_of_ts):
                        ip_as_int = ipv4_to_int(ip_address)
                        insertpos = bisect.bisect(sortedarray, ip_as_int)
                        sortedarray.insert(insertpos, ip_as_int)
                        retarray.insert(insertpos, lease_rec)
        return retarray

##############################################################################

def esc(v):
    """Escape a Prometheus label value (backslash, quote, newline)."""
    return str(v).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


def write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.dhcp.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)          # atomic on the same filesystem
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_leases(path, retries=2, delay=2):
    for attempt in range(retries + 1):
        try:
            with open(path, 'r') as f:
                return parse_leases_file(f)
        except OSError:
            raise                      # missing/permissions: retrying won't help
        except Exception:
            if attempt == retries:
                raise
            time.sleep(delay)          # possibly caught dhcpd mid-write


def render(leases, now):
    out = []
    for lease in select_active_leases(leases, now):
        remaining = 'never' if lease['ends'] == 'never' else str(lease['ends'] - now)
        labels = 'ip="%s",mac="%s",time="%s"' % (
            esc(lease['ip_address']), esc(lease['hardware']), esc(remaining))
        if lease['client-hostname']:
            labels += ',ddns="%s"' % esc(lease['client-hostname'])
        out.append('dhcpd_active_leases{%s} 1' % labels)
    out.append('dhcpd_leases_last_success_timestamp_seconds %d' % time.time())
    return '\n'.join(out) + '\n'


def main():
    parser = argparse.ArgumentParser(description='isc leases to node exporter textfile')
    parser.add_argument('-f', '--file', type=str, help='dhcpd.leases',
                        default='/var/lib/dhcpd/dhcpd.leases')
    parser.add_argument('-o', '--output', type=str,
                        help='write atomically to this .prom file (default: stdout)')
    args = parser.parse_args()
    try:
        text = render(load_leases(args.file), timestamp_now())
        if args.output:
            write_atomic(args.output, text)
        else:
            sys.stdout.write(text)
    except Exception as e:
        print('dhcp.py: %s: %s' % (type(e).__name__, e), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())