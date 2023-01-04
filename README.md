# Simple Python SMART exporter for Prometheus on FreeBSD

This is a simple SMART exporter as provider for the [Prometheus  time series database
and monitoring system](https://prometheus.io/) written in Python. It uses
the [prometheus-client](https://github.com/prometheus/client_python) Python
package to do the main work of running the webservice and managing the gauges.
It's just a wrapper that periodically calls ```smartmonctl``` from [smartmontools](https://www.smartmontools.org/)
to gather information about the filesystems disks which is then provided on
the specified TCP port where it's collected by Prometheus at the specified
scrape interval. This scraper uses ```geom disk list``` to determine which disks
should be queried (__thus it only works on FreeBSD, not on Linux__).

Since this exporter scrapes the output of the CLI tools it may break with
any software update and might only work with particular versions of those
tools. It has been tested on:

* FreeBSD 11.2
* FreeBSD 12.2
* FreeBSD 12.3

## Exported metrics

* For each disk the following parameters are exposed via ```geom``` (serial
	and name used as labels):
   * Media size (```mediasize```)
	 * Sector size (```sectorsize```)
	 * Rotation speed for rotating harddisks (```rotationrate```)
* All smart parameters of every disk that are available via ```smartctl``` (serial
	and name used as labels). These are published with ```smart_``` prefix.

## Installation

The package can either be installed from PyPI

```
pip install smartexporter-tspspi
```

or form a package downloaded directly from the ```tar.gz``` or ```whl``` from
the [releases](https://github.com/tspspi/smartexporter/releases):

```
pip install smartexporter-tspspi.tar.gz
```

Note that ```smartmontools``` are required on the target system. They can
be installed using ```pkg```:

```
pkg install smartmontools
```

## Usage

```
usage: smartexporter [-h] [-f] [--uid UID] [--gid GID] [--chroot CHROOT] [--pidfile PIDFILE] [--loglevel LOGLEVEL] [--logfile LOGFILE] [--port PORT] [--interval INTERVAL]

SMART data exporter daemon

optional arguments:
  -h, --help           show this help message and exit
  -f, --foreground     Do not daemonize - stay in foreground and dump debug information to the terminal
  --uid UID            User ID to impersonate when launching as root
  --gid GID            Group ID to impersonate when launching as root
  --chroot CHROOT      Chroot directory that should be switched into
  --pidfile PIDFILE    PID file to keep only one daemon instance running
  --loglevel LOGLEVEL  Loglevel to use (debug, info, warning, error, critical). Default: error
  --logfile LOGFILE    Logfile that should be used as target for log messages
  --port PORT          Port to listen on (default 9248)
  --interval INTERVAL  Interval in seconds in which data is gathered (default 300 seconds)
```
