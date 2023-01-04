#!/usr/bin/env python3

import argparse
import sys
import logging

import signal, lockfile, grp, os

from pwd import getpwnam
from daemonize import Daemonize

from prometheus_client import start_http_server, Gauge
from typing import Dict
import subprocess
import time

class SMARTExporterDaemon:
	def __init__(self, args, logger):
		self.args = args
		self.logger = logger
		self.terminate = False
		self.rereadConfig = True

		self.smartMetricDescriptions = {
		}

		# Note: Gauges for SMART parameters are created dynamically ...
		self.metrics = {
			'mediasize' : Gauge("geom_mediasize", "Media size of disks", labelnames = [ 'serial', 'name' ]),
			'sectorsize' : Gauge("geom_sectorsize", "Size of sectors on disk", labelnames = [ 'serial', 'name' ]),
			'rotationrate' : Gauge("geom_rotationrate", "Rotation rate of disk", labelnames = [ 'serial', 'name' ])
		}

	def SuffixNotationToBytes(self, inp):
		if inp[-1] == 'K':
			return float(inp[:-1]) * 1e3
		if inp[-1] == 'M':
			return float(inp[:-1]) * 1e6
		if inp[-1] == 'G':
			return float(inp[:-1]) * 1e9
		if inp[-1] == 'T':
			return float(inp[:-1]) * 1e12
		else:
			return float(inp)

	def getSMARTData(self, geom):
		p = subprocess.Popen("smartctl -A /dev/{}".format(geom), stdout=subprocess.PIPE, shell=True)
		(output, err) = p.communicate()
		status = p.wait()

		output = output.decode("utf-8").split("\n")
		for i in range(len(output)):
			output[i] = output[i].strip()

		smartdata = {}
		skippedHeader = False

		for line in output:
			if not skippedHeader:
				if line.startswith("ID#"):
					skippedHeader = True
			else:
				parts = line.split()
				if len(parts) == 10:
					attId = int(parts[0])
					attName = parts[1].replace('-', '').replace('_', '')
					attFlags = parts[2]
					attVal = int(parts[3])
					attWorst = int(parts[4])
					attThres = int(parts[5])
					attType = parts[6]
					attUpdated = parts[7]
					attRaw = parts[9]

					smartdata[attName] = {
						'id' : attId,
						'flags' : attFlags,
						'value' : attVal,
						'worst' : attWorst,
						'threshold' : attThres,
						'type' : attType,
						'updated' : attUpdated,
						'rawValue' : attRaw
					}

		return smartdata

	def parseSmart(self, metrics):
		p = subprocess.Popen("geom disk list", stdout=subprocess.PIPE, shell=True)
		(output, err) = p.communicate()
		status = p.wait()

		output = output.decode("utf-8").split("\n")
		for i in range(len(output)):
			output[i] = output[i].strip()

		disks = { }
		currentGeom = False

		for line in output:
			if line.startswith("Geom name:"):
				currentGeom = line[len("Geom name: "):].strip()

				disks[currentGeom] = {}


			try:
				if line.startswith("Mediasize: "):
					msize = line[len("Mediasize: "):]
					msize = msize.split(" ")
					msize = msize[0]
					if currentGeom:
						disks[currentGeom]['mediasize'] = int(msize)
				if line.startswith("Sectorsize:"):
					if currentGeom:
						disks[currentGeom]['sectorsize'] = int(line[len("Sectorsize: "):].strip())
				if line.startswith("descr:"):
					if currentGeom:
						disks[currentGeom]['description'] = line[len("descr: "):].strip()
				if line.startswith("lunid:"):
					if currentGeom:
						disks[currentGeom]['lunid'] = line[len("lunid: "):].strip()
				if line.startswith("ident:"):
					if currentGeom:
						disks[currentGeom]['serial'] = line[len("ident: "):].strip()
				if line.startswith("rotationrate:"):
					if currentGeom:
						disks[currentGeom]['rotationrate'] = int(line[len("rotationrate: "):].strip())
				if line.startswith("Stripesize:"):
					if currentGeom:
						disks[currentGeom]['stripesize'] = int(line[len("Stripesize: "):].strip())
			except ValueError:
				pass

		# Now query the SMART data
		for currentGeom in disks:
			disks[currentGeom]['smart'] = self.getSMARTData(currentGeom)

		# And insert into our gauges ...
		for currentGeom in disks:
			# First the GEOM data
			if 'mediasize' in disks[currentGeom]:
				metrics['mediasize'].labels(serial = disks[currentGeom]['serial'], name = currentGeom).set(disks[currentGeom]['mediasize'])
			if 'sectorsize' in disks[currentGeom]:
				metrics['sectorsize'].labels(serial = disks[currentGeom]['serial'], name = currentGeom).set(disks[currentGeom]['sectorsize'])
			if 'rotationrate' in disks[currentGeom]:
				metrics['rotationrate'].labels(serial = disks[currentGeom]['serial'], name = currentGeom).set(disks[currentGeom]['rotationrate'])

			# Dynamically generated SMART metrics
			for smartatt in disks[currentGeom]['smart']:
				if not 'rawValue' in disks[currentGeom]['smart'][smartatt]:
					continue
				if not "smart_{}".format(smartatt) in metrics:
					description = "No description"
					if smartatt in self.smartMetricDescriptions:
						description = self.smartMetricDescriptions[smartatt]
					metrics["smart_{}".format(smartatt)] = Gauge("smart_{}".format(smartatt), description, labelnames = [ 'serial', 'name' ])
				metrics["smart_{}".format(smartatt)].labels(serial = disks[currentGeom]['serial'], name = currentGeom).set(disks[currentGeom]['smart'][smartatt]['rawValue'])

	def signalSigHup(self, *args):
		self.rereadConfig = True
	def signalTerm(self, *args):
		self.terminate = True
	def __enter__(self):
		return self
	def __exit__(self, type, value, tb):
		pass

	def run(self):
		signal.signal(signal.SIGHUP, self.signalSigHup)
		signal.signal(signal.SIGTERM, self.signalTerm)
		signal.signal(signal.SIGINT, self.signalTerm)

		self.logger.info("Service running")

		start_http_server(self.args.port)
		while True:
			self.parseSmart(self.metrics)

			if self.terminate:
				break

			time.sleep(self.args.interval)

		self.logger.info("Shutting down due to user request")

def mainDaemon():
	parg = parseArguments()
	args = parg['args']
	logger = parg['logger']

	logger.debug("Daemon starting ...")
	with SMARTExporterDaemon(args, logger) as exporterDaemon:
		exporterDaemon.run()

def parseArguments():
	ap = argparse.ArgumentParser(description = 'SMART data exporter daemon')
	ap.add_argument('-f', '--foreground', action='store_true', help="Do not daemonize - stay in foreground and dump debug information to the terminal")

	ap.add_argument('--uid', type=str, required=False, default=None, help="User ID to impersonate when launching as root")
	ap.add_argument('--gid', type=str, required=False, default=None, help="Group ID to impersonate when launching as root")
	ap.add_argument('--chroot', type=str, required=False, default=None, help="Chroot directory that should be switched into")
	ap.add_argument('--pidfile', type=str, required=False, default="/var/run/smartexporter.pid", help="PID file to keep only one daemon instance running")
	ap.add_argument('--loglevel', type=str, required=False, default="error", help="Loglevel to use (debug, info, warning, error, critical). Default: error")
	ap.add_argument('--logfile', type=str, required=False, default="/var/log/smartexporter.log", help="Logfile that should be used as target for log messages")

	ap.add_argument('--port', type=int, required=False, default=9248, help="Port to listen on (default 9248)")
	ap.add_argument('--interval', type=int, required=False, default=300, help="Interval in seconds in which data is gathered (default 300 seconds)")

	args = ap.parse_args()
	loglvls = {
		"DEBUG"     : logging.DEBUG,
		"INFO"      : logging.INFO,
		"WARNING"   : logging.WARNING,
		"ERROR"     : logging.ERROR,
		"CRITICAL"  : logging.CRITICAL
	}
	if not args.loglevel.upper() in loglvls:
		print("Unknown log level {}".format(args.loglevel.upper()))
		sys.exit(1)

	logger = logging.getLogger()
	logger.setLevel(loglvls[args.loglevel.upper()])
	if args.logfile:
		fileHandleLog = logging.FileHandler(args.logfile)
		logger.addHandler(fileHandleLog)

	return { 'args' : args, 'logger' : logger }

def mainStartup():
	parg = parseArguments()
	args = parg['args']
	logger = parg['logger']

	daemonPidfile = args.pidfile
	daemonUid = None
	daemonGid = None
	daemonChroot = "/"

	if args.uid:
		try:
			args.uid = int(args.uid)
		except ValueError:
			try:
				args.uid = getpwnam(args.uid).pw_uid
			except KeyError:
				logger.critical("Unknown user {}".format(args.uid))
				print("Unknown user {}".format(args.uid))
				sys.exit(1)
		daemonUid = args.uid
	if args.gid:
		try:
			args.gid = int(args.gid)
		except ValueError:
			try:
				args.gid = grp.getgrnam(args.gid)[2]
			except KeyError:
				logger.critical("Unknown group {}".format(args.gid))
				print("Unknown group {}".format(args.gid))
				sys.exit(1)

		daemonGid = args.gid

	if args.chroot:
		if not os.path.isdir(args.chroot):
			logger.critical("Non existing chroot directors {}".format(args.chroot))
			print("Non existing chroot directors {}".format(args.chroot))
			sys.exit(1)
		daemonChroot = args.chroot

	if args.foreground:
		logger.debug("Launching in foreground")
		with SMARTExporterDaemon(args, logger) as smartDaemon:
			smartDaemon.run()
	else:
		logger.debug("Daemonizing ...")
		daemon = Daemonize(
			app="SMART exporter",
			action=mainDaemon,
			pid=daemonPidfile,
			user=daemonUid,
			group=daemonGid,
			chdir=daemonChroot
		)
		daemon.start()


if __name__ == "__main__":
	mainStartup()
