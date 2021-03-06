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
import daemon
import db
import re
import time

from trace_event import *

# TODO(nduca): is Stub the right word for this class? Mehh
class DBStub(object):
  def __init__(self, settings, server):
    self.db = db.DB(settings)
    self.db.needs_indexing.add_listener(self.on_db_needs_indexing)
    self.server = server
    self.hi_idle_hook_added = False

    server.add_json_route('/begin_reindex', self.begin_reindex, ['POST'])
    server.add_json_route('/dirs/add', self.add_dir, ['POST'])
    server.add_json_route('/dirs', self.list_dirs, ['GET'])
    server.add_json_route('/dirs/([a-zA-Z0-9]+)', self.get_dir, ['GET'])
    server.add_json_route('/dirs/([a-zA-Z0-9]+)', self.delete_dir, ['DELETE'])
    server.add_json_route('/ignores', self.get_ignores, ['GET'])
    server.add_json_route('/ignores/add', self.ignores_add, ['POST'])
    server.add_json_route('/ignores/remove', self.ignores_remove, ['POST'])
    server.add_json_route('/sync', self.sync, ['POST'])
    server.add_json_route('/status', self.status, ['GET'])
    server.add_json_route('/search', self.search, ['POST'])
    if not self.db.is_up_to_date:
      self.on_db_needs_indexing()
    self.server.lo_idle.add_listener(self.on_daemon_lo_idle)
    self._last_flush_time = 0

  def on_db_needs_indexing(self):
    if self.hi_idle_hook_added:
      return
    self.server.hi_idle.add_listener(self.on_daemon_hi_idle)

  def on_daemon_lo_idle(self):
    # self.db.check_up_to_date_a_bit_more()
    if time.time() - self._last_flush_time > 5:
      trace_flush()
      self._last_flush_time = time.time()

  def on_daemon_hi_idle(self):
    self.db.step_indexer()

    if self.db.is_up_to_date:
      self.server.hi_idle.remove_listener(self.on_daemon_hi_idle)
      self.hi_idle_hook_added = False

  def add_dir(self, m, verb, data):
    d = self.db.add_dir(data["path"])
    return {"id": d.id,
            "status": 'OK'}

  def list_dirs(self, m, verb, data):
    return map(lambda d: d.__getstate__(), self.db.dirs)

  def get_dir(self, m, verb, data):
    id = m.group(1)
    for d in self.db.dirs:
      if d.id == id:
        return d.__getstate__()
    raise daemon.NotFoundException()

  def delete_dir(self, m, verb, data):
    id = m.group(1)
    for d in self.db.dirs:
      if d.id == id:
        self.db.delete_dir(d)
        return {"status": 'OK'}
    raise daemon.NotFoundException()    

  def get_ignores(self, m, verb, data):
    return self.db.ignores

  def ignores_add(self, m, verb, data):
    self.db.ignore(data)
    return {"status": "OK"}

  def ignores_remove(self, m, verb, data):
    try:
      self.db.unignore(data)
    except Exception:
      raise daemon.SilentException()
    return {"status": "OK"}

  def search(self, m, verb, data):
    return self.db.search(data).as_dict()

  def sync(self, m, verb, data):
    self.db.sync()
    return {"status": "OK"}

  def status(self, m, verb, data):
    return self.db.status().as_dict()

  def begin_reindex(self, m, verb, data):
    self.db.begin_reindex()
    return {"status": "OK"}
