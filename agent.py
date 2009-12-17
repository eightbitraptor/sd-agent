#!/usr/bin/env python
'''
	Server Density
	www.serverdensity.com
	----
	A web based server resource monitoring application

	Licensed under Simplified BSD License (see LICENSE)
	(C) Boxed Ice 2009 all rights reserved
'''

# General config
agentConfig = {}
agentConfig['debugMode'] = 0
agentConfig['checkFreq'] = 60

agentConfig['version'] = '1.4.1'

# Core modules
import ConfigParser
import logging
import os
import re
import sched
import sys
import time

# Check we're not using an old version of Python. We need 2.4 above because some modules (like subprocess)
# were only introduced in 2.4.
if int(sys.version_info[1]) <= 3:
	print 'You are using an outdated version of Python. Please update to v2.4 or above (v3 is not supported).'
	sys.exit(2)
	
# Custom modules
from checks import checks
from daemon import Daemon

# Config handling
try:
	path = os.path.realpath(__file__)
	path = os.path.dirname(path)
	
	config = ConfigParser.ConfigParser()
	if os.path.exists('/etc/sd-agent.cfg'):
		config.read('/etc/sd-agent.cfg')
	else:
		config.read(path + '/config.cfg')
	
	# Core config
	agentConfig['sdUrl'] = config.get('Main', 'sd_url')
	if agentConfig['sdUrl'].endswith('/'):
		agentConfig['sdUrl'] = agentConfig['sdUrl'][:-1]
	agentConfig['agentKey'] = config.get('Main', 'agent_key')
	agentConfig['tmpDirectory'] = '/tmp/' # default which may be overriden in the config later
	agentConfig['pidfile_location'] = agentConfig['tmpDirectory']
	
	# Optional config
	# Also do not need to be present in the config file (case 28326).	
	if config.has_option('Main', 'apache_status_url'):
		agentConfig['apacheStatusUrl'] = config.get('Main', 'apache_status_url')		
		
	if config.has_option('Main', 'mysql_server'):
		agentConfig['MySQLServer'] = config.get('Main', 'mysql_server')
		
	if config.has_option('Main', 'mysql_user'):
		agentConfig['MySQLUser'] = config.get('Main', 'mysql_user')
		
	if config.has_option('Main', 'mysql_pass'):
		agentConfig['MySQLPass'] = config.get('Main', 'mysql_pass')
	
	if config.has_option('Main', 'nginx_status_url'):	
		agentConfig['nginxStatusUrl'] = config.get('Main', 'nginx_status_url')

	if config.has_option('Main', 'tmp_directory'):
		agentConfig['tmpDirectory'] = config.get('Main', 'tmp_directory')
		
	# Stats reporting, optional (supports older agent versions without this config value)
	if config.has_option('Main', 'report_anon_stats'):
		agentConfig['reportAnonStats'] = config.get('Main', 'report_anon_stats')

	if config.has_option('Main', 'pidfile_location'):
		agentConfig['pidfile_location'] = config.get('Main', 'pidfile_location')
	
except ConfigParser.NoSectionError, e:
	print 'Config file not found or incorrectly formatted'
	sys.exit(2)
	
except ConfigParser.ParsingError, e:
	print 'Config file not found or incorrectly formatted'
	sys.exit(2)
	
except ConfigParser.NoOptionError, e:
	print 'There are some items missing from your config file, but nothing fatal'
	
# Check to make sure the default config values have been changed (only core config values)
if agentConfig['sdUrl'] == 'http://example.serverdensity.com' or agentConfig['agentKey'] == 'keyHere':
	print 'You have not modified config.cfg for your server'
	sys.exit(2)

# Check to make sure sd_url is in correct
if re.match('http(s)?(\:\/\/)[a-zA-Z0-9_\-]+\.(serverdensity.com)', agentConfig['sdUrl']) == None:
	print 'Your sd_url is incorrect. It needs to be in the form http://example.serverdensity.com (or using https)'
	sys.exit(2)
	
# Check apache_status_url is not empty (case 27073)
if agentConfig['apacheStatusUrl'] == None:
	print 'You must provide a config value for apache_status_url. If you do not wish to use Apache monitoring, leave it as its default value - http://www.example.com/server-status/?auto'
	sys.exit(2) 

if 'nginxStatusUrl' in agentConfig and agentConfig['nginxStatusUrl'] == None:
	print 'You must provide a config value for nginx_status_url. If you do not wish to use Nginx monitoring, leave it as its default value - http://www.example.com/nginx_status'
	sys.exit(2)

# Override the generic daemon class to run our checks
class agent(Daemon):	
	
	def run(self):	
		agentLogger = logging.getLogger('agent')
		
		agentLogger.debug('Collecting basic system stats')
		
		# Get some basic system stats to post back for development/testing
		import platform
		systemStats = {'machine': platform.machine(), 'platform': sys.platform, 'processor': platform.processor(), 'pythonV': platform.python_version()}
		
		if sys.platform == 'linux2':			
			systemStats['nixV'] = platform.dist()
			
		elif sys.platform == 'darwin':
			systemStats['macV'] = platform.mac_ver()
		
		agentLogger.debug('System: ' + str(systemStats))
		
		# We use the system stats in the log but user might not want them posted back
		if 'reportAnonStats' in agentConfig and agentConfig['reportAnonStats'] == 'no':	
			systemStats = None
				
		agentLogger.debug('Creating checks instance')
		
		# Checks instance
		c = checks(agentConfig)
		
		# Schedule the checks
		agentLogger.debug('Scheduling checks every ' + str(agentConfig['checkFreq']) + ' seconds')
		s = sched.scheduler(time.time, time.sleep)
		c.doChecks(s, True, systemStats) # start immediately (case 28315)
		s.run()

# Control of daemon		
if __name__ == '__main__':	
	# Logging
	if agentConfig['debugMode']:
		logFile = os.path.join(agentConfig['tmpDirectory'], 'sd-agent.log')
		logging.basicConfig(filename=logFile, filemode='w', level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
	
	mainLogger = logging.getLogger('main')		
	mainLogger.debug('Agent called')
	mainLogger.debug('Agent version: ' + agentConfig['version'])
	
	argLen = len(sys.argv)
	
	if argLen == 3 or argLen == 4: # needs to accept case when --clean is passed
		if sys.argv[2] == 'init':
			pidFile = '/var/run/sd-agent.pid'
			
	else:
		pidFile = os.path.join(agentConfig['pidfile_location'], 'sd-agent.pid')
	
	if argLen == 4 and sys.argv[3] == '--clean':
		mainLogger.debug('Agent called with --clean option, removing .pid')
		try:
			os.remove(pidFile)
		except OSError:
			# Did not find pid file
			pass
	
	# Daemon instance from agent class
	daemon = agent(pidFile)
	
	# Control options
	if argLen == 2 or argLen == 3 or argLen == 4:
		if 'start' == sys.argv[1]:
			mainLogger.debug('Start daemon')
			daemon.start()
			
		elif 'stop' == sys.argv[1]:
			mainLogger.debug('Stop daemon')
			daemon.stop()
			
		elif 'restart' == sys.argv[1]:
			mainLogger.debug('Restart daemon')
			daemon.restart()
			
		elif 'foreground' == sys.argv[1]:
			mainLogger.debug('Running in foreground')
			daemon.run()
			
		elif 'status' == sys.argv[1]:
			mainLogger.debug('Checking agent status')
			
			try:
				pf = file(pidFile,'r')
				pid = int(pf.read().strip())
				pf.close()
			except IOError:
				pid = None
			except SystemExit:
				pid = None
				
			if pid:
				print 'sd-agent is running as pid %s.' % pid
			else:
				print 'sd-agent is not running.'

		elif 'update' == sys.argv[1]:
			mainLogger.debug('Updating agent')
			
			import httplib
			import platform
			import urllib2
			
			print 'Checking if there is a new version';
			
			# Get the latest version info
			try: 
				mainLogger.debug('Update: checking for update')
				
				request = urllib2.urlopen('http://www.serverdensity.com/agentupdate/')
				response = request.read()
				
			except urllib2.HTTPError, e:
				print 'Unable to get latest version info - HTTPError = ' + str(e)
				sys.exit(2)
				
			except urllib2.URLError, e:
				print 'Unable to get latest version info - URLError = ' + str(e)
				sys.exit(2)
				
			except httplib.HTTPException, e:
				print 'Unable to get latest version info - HTTPException'
				sys.exit(2)
				
			except Exception, e:
				import traceback
				print 'Unable to get latest version info - Exception = ' + traceback.format_exc()
				sys.exit(2)
			
			mainLogger.debug('Update: importing json/minjson')
			
			# We need to return the data using JSON. As of Python 2.6+, there is a core JSON
			# module. We have a 2.4/2.5 compatible lib included with the agent but if we're
			# on 2.6 or above, we should use the core module which will be faster
			pythonVersion = platform.python_version_tuple()
			
			# Decode the JSON
			if int(pythonVersion[1]) >= 6: # Don't bother checking major version since we only support v2 anyway
				import json
				
				mainLogger.debug('Update: decoding JSON (json)')
				
				try:
					updateInfo = json.loads(response)
				except Exception, e:
					print 'Unable to get latest version info. Try again later.'
					sys.exit(2)
				
			else:
				import minjson
				
				mainLogger.debug('Update: decoding JSON (minjson)')
				
				try:
					updateInfo = minjson.safeRead(response)
				except Exception, e:
					print 'Unable to get latest version info. Try again later.'
					sys.exit(2)
			
			# Do the version check	
			if updateInfo['version'] != agentConfig['version']:			
				import md5 # I know this is depreciated, but we still support Python 2.4 and hashlib is only in 2.5. Case 26918
				import urllib
				
				print 'A new version is available.'
				
				def downloadFile(agentFile, recursed = False):
					mainLogger.debug('Update: downloading ' + agentFile['name'])					
					print 'Downloading ' + agentFile['name']
					
					downloadedFile = urllib.urlretrieve('http://www.serverdensity.com/downloads/sd-agent/' + agentFile['name'])
					
					# Do md5 check to make sure the file downloaded properly
					checksum = md5.new()
					f = file(downloadedFile[0], 'rb')
					
					# Although the files are small, we can't guarantee the available memory nor that there
					# won't be large files in the future, so read the file in small parts (1kb at time)
					while True:
						part = f.read(1024)
						
						if not part: 
							break # end of file
					
						checksum.update(part)
						
					f.close()
					
					# Do we have a match?
					if checksum.hexdigest() == agentFile['md5']:
						return downloadedFile[0]
						
					else:
						# Try once more
						if recursed == False:
							downloadFile(agentFile, True)
						
						else:
							print agentFile['name'] + ' did not match its checksum - it is corrupted. This may be caused by network issues so please try again in a moment.'
							sys.exit(2)
				
				# Loop through the new files and call the download function
				for agentFile in updateInfo['files']:
					agentFile['tempFile'] = downloadFile(agentFile)			
				
				# If we got to here then everything worked out fine. However, all the files are still in temporary locations so we need to move them
				# This is to stop an update breaking a working agent if the update fails halfway through
				import os
				import shutil # Prevents [Errno 18] Invalid cross-device link (case 26878) - http://mail.python.org/pipermail/python-list/2005-February/308026.html
				
				for agentFile in updateInfo['files']:
					mainLogger.debug('Update: updating ' + agentFile['name'])
					print 'Updating ' + agentFile['name']
					
					try:
						if os.path.exists(agentFile['name']):
							os.remove(agentFile['name'])
							
						shutil.move(agentFile['tempFile'], agentFile['name'])
					
					except OSError:
						print 'An OS level error occurred. You will need to manually re-install the agent by downloading the latest version from http://www.serverdensity.com/downloads/sd-agent.tar.gz. You can copy your config.cfg to the new install'
						sys.exit(2)
				
				mainLogger.debug('Update: done')
				
				print 'Update completed. Please restart the agent (python agent.py restart).'
				
			else:
				print 'The agent is already up to date'
		
		else:
			print 'Unknown command'
			sys.exit(2)
			
		sys.exit(0)
		
	else:
		print 'usage: %s start|stop|restart|status|update' % sys.argv[0]
		sys.exit(2)