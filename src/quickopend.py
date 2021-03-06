# Copyright 2011 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import httplib
import json
import logging
import sys
import optparse
import os
import re
import time

sys.path.append(os.path.join(os.path.dirname(__file__), "../third_party/py_trace_event/"))
try:
  from trace_event import *
except:
  print "Could not find py_trace_event. Did you forget 'git submodule update --init'"
  sys.exit(255)

import src.daemon
import src.db_stub
import src.settings
import src.prelaunchd

def load_settings(options):
  settings_file = os.path.expanduser(options.settings)
  settings = src.settings.Settings(settings_file)
  settings.register('host', str, 'localhost')
  settings.register('port', int, 10248)

  if options.port:
    settings.port = int(options.port)

  if options.host != None:
    settings.host = options.host

  return settings

def is_port_listening(host, port):
  import socket
  s = socket.socket()
  try:
    s.connect((host, port))
  except socket.error:
    return False
  s.close()
  return True

def CMDrun(parser, args):
  """Runs the quickopen daemon"""
  (options, args) = parser.parse_args(args)
  settings = load_settings(options)
  if is_port_listening(settings.host, settings.port):
    print "%s:%s in use. Try 'quickopend stop' first?" % (settings.host, settings.port)
    return 255
  prelaunchdaemon = None
  try:
    daemon = src.daemon.create(settings.host, settings.port, options.test)
    db_stub = src.db_stub.DBStub(settings, daemon)
    prelaunchd = src.prelaunchd.PrelaunchDaemon(daemon)
    daemon.run()
  finally:
    if prelaunchdaemon:
      prelaunchdaemon.stop()
  return 0


def CMDstatus(parser, args):
  """Gets the status of the quickopen daemon"""
  (options, args) = parser.parse_args(args)
  settings = load_settings(options)
  if not is_port_listening(settings.host, settings.port):
    print "Not running"
    return 255

  try:
    conn = httplib.HTTPConnection(settings.host, settings.port, True)
    conn.request('GET', '/status')
    resp = conn.getresponse()
  except:
    print "Not responding"
    return 255

  if resp.status != 200:
    print "Service running on %s:%i is probaby not quickopend" % (settings.host, settings.port)
    return 255

  status_str = resp.read()
  status = json.loads(status_str)
  print status["status"]
  return 0

def CMDstop(parser, args):
  """Gets the status of the quickopen daemon"""
  (options, args) = parser.parse_args(args)
  settings = load_settings(options)
  try:
    conn = httplib.HTTPConnection(settings.host, settings.port, True)
    conn.request('GET', '/exit')
    resp = conn.getresponse()
  except:
    print "Not responding"
    return 255

  if resp.status != 200:
    print "Service running on %s:%i is probaby not quickopend" % (settings.host, settings.port)
    return 255

  status_str = resp.read()
  status = json.loads(status_str)
  if status["status"] != "OK":
    print "Stop failed with unexpected result %s" % status["status"]
    return 255
  print "Existing quickopend on %s:%i stopped" % (settings.host, settings.port)
  return 0

def CMDrestart(parser, in_args):
  """Restarts the quickopen daemon"""
  (options, args) = parser.parse_args(in_args)
  settings = load_settings(options)

  ret = CMDstop(parser, args)
  if ret != 0:
    return ret
  time.sleep(0.25)

  tries = 0
  while is_port_listening(settings.host, settings.port) and tries < 10:
    tries += 1
    time.sleep(0.1)
  if tries == 10:
    print "Previous quickopend did not stop."
    return 255
  pid = os.fork()
  if pid == 0:
    CMDrun(parser, args)
    return 0
  return 0

# Subcommand addins to optparse, taken from git-cl.py,
# http://src.chromium.org/svn/trunk/tools/depot_tools/git_cl.py
###########################################################################

def Command(name):
  return getattr(sys.modules[__name__], 'CMD' + name, None)


def CMDhelp(parser, args):
  """print list of commands or help for a specific command"""
  _, args = parser.parse_args(args)
  if len(args) == 1:
    return main(args + ['--help'])
  parser.print_help()
  return 0


def GenUsage(parser, command):
  """Modify an OptParse object with the function's documentation."""
  obj = Command(command)
  more = getattr(obj, 'usage_more', '')
  if command == 'help':
    command = '<command>'
  else:
    # OptParser.description prefer nicely non-formatted strings.
    parser.description = re.sub('[\r\n ]{2,}', ' ', obj.__doc__)
  parser.set_usage('usage: %%prog %s [options] %s' % (command, more))


def main(argv):
  """Doesn't parse the arguments here, just find the right subcommand to
  execute."""

  # Do it late so all commands are listed.
  CMDhelp.usage_more = ('\n\nCommands are:\n' + '\n'.join([
      '  %-10s %s' % (fn[3:], Command(fn[3:]).__doc__.split('\n')[0].strip())
      for fn in dir(sys.modules[__name__]) if fn.startswith('CMD')]))
  parser = optparse.OptionParser()
  parser.add_option('--host', dest='host', action='store', help='Hostname to listen on')
  parser.add_option('--port', dest='port', action='store', help='Port to run on')
  parser.add_option('--settings', dest='settings', action='store', default='~/.quickopend', help='Settings file to use')
  parser.add_option('--test', dest='test', action='store_true', default=False, help='Adds test hooks')
  parser.add_option('--trace', dest='trace', action='store_true', default=False, help='Records performance tracing information to %s.trace' % sys.argv[0])
  parser.add_option(
      '-v', '--verbose', action='count', default=0,
      help='Increase verbosity level (repeat as needed)')
  old_parser_args = parser.parse_args
  def Parse(args):
    options, args = old_parser_args(args)
    if options.verbose >= 2:
      logging.basicConfig(level=logging.DEBUG)
    elif options.verbose:
      logging.basicConfig(level=logging.INFO)
    else:
      logging.basicConfig(level=logging.WARNING)
    if options.trace:
      trace_enable("%s.trace" % sys.argv[0])
    return options, args
  parser.parse_args = Parse

  non_switch_args = [i for i in argv if not i.startswith('-')]
  if non_switch_args:
    command = Command(non_switch_args[0])
    if command:
      # "fix" the usage and the description now that we know the subcommand.
      GenUsage(parser, non_switch_args[0])
      new_args = list(argv)
      new_args.remove(non_switch_args[0])
      return command(parser, new_args)
    # Not a known command. Default to help.
    GenUsage(parser, 'help')
    return CMDhelp(parser, argv)
  else: # default command
    GenUsage(parser, 'run')
    return CMDrun(parser, argv)
