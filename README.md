# isc-leases-node-exporter

Tool to import ISC-DHCP-SERVER active (valid) leases to node exporter text file

Requirements:

    ISC-DHCP-SERVER
    Python 3.9+

crontab:

*/5 * * * * /opt/monitoring_tools/node_exporter/scripts_collector/dhcp.py > /opt/monitoring_tools/node_exporter/textfile_collector/dhcp.prom

by default use "/var/lib/dhcpd/dhcpd.leases", you can change path with -f argument

Grafana dashboard:
![alt text](https://github.com/Fritnes/isc-leases-node-exporter/blob/main/grafana-dashboard/dashboard.png?raw=true)

Disclaimer:
Major code source was not developed by Me.
I've found this (https://github.com/websvcPT/isc-lease-tool) while working on a project, made some minor changes.
As this was very helpfull for me, I thought it would be nice to share it with others-
If any one know the source of if please let me know, and I'll give the acording credits.
