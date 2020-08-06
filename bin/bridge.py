#!/bin/python3

import os
import json
import time
import logging
from queue import Queue
from threading import Thread, Lock

from tornado.ioloop import IOLoop
from tornado.httpserver import HTTPServer
from tornado.web import Application, RequestHandler, StaticFileHandler

from crontab import RootCronTabDriver

__parallel_number__ = 1
__trigger__ = "TRIGGERPATH"
__serialization__ = "JSONPATH"
__timeout_alarm__ = 1  # minutes
__alarm_gap__ = 10  # minutes

_default_global_context = None
_tasks_json = {"tasks": []}
_default_root_cron = RootCronTabDriver()


def prepare_logging():
    logging.basicConfig(
        format='%(asctime)s [%(threadName)s] [%(name)s] [%(levelname)s] %(filename)s[line:%(lineno)d] %(message)s',
        level=logging.INFO
    )


class AtomicBoolean:
    def __init__(self, init=False):
        self._var = init
        self._lock = Lock()

    def get(self):
        return self._var

    def set(self, v):
        with self._lock:
            self._var = v


class Starter:
    @staticmethod
    def deserialize(path):
        global _tasks_json
        with open(path, 'r+') as fp:
            _tasks_json = json.loads(fp.read())
            if 'tasks' not in _tasks_json:
                _tasks_json = {"tasks": []}

    @staticmethod
    def serialize(path):
        global _tasks_json
        with open(path, 'w+') as fp:
            fp.write(json.dumps(_tasks_json, indent=2, sort_keys=True))

    @staticmethod
    def register():
        # logging.info("-- ", json.dumps(_tasks_json))
        _default_root_cron.remove_task(__trigger__, regex=True)
        tasks: list = _tasks_json['tasks']
        for task in tasks:
            cron_time: list = task['cron'].split(' ')
            if len(cron_time) != 5:
                logging.error("[cron] format error - %s." % task['cron'])
                continue
            _default_root_cron.create_task(
                "%s %s" % (__trigger__, task['uuid']),
                minute=cron_time[0], hour=cron_time[1],
                day_of_month=cron_time[2], month=cron_time[3],
                day_of_week=cron_time[4]
            )
        logging.info("[register] task: " + json.dumps(_tasks_json, indent=2))


class SinglePlankBridge(Thread):
    _is_working = AtomicBoolean()
    _tasks_infos = {}
    _tasks_infos_v2 = []
    _tasks_queue = None
    _task_locker = Lock()
    _inner_worker = None

    def __init__(self, max_tasks_number=10):
        super().__init__()
        self._tasks_queue = Queue(max_tasks_number)
        self._is_working.set(True)
        self._inner_worker = Thread(
            target=self._daemon,
            args=(),
        )

    def close(self):
        self._is_working.set(False)

    def go(self, task: dict):
        with self._task_locker:
            self._tasks_infos_v2.append({
                'uuid': task['uuid'],
                'arg': task,
                'beg': 0,
                'add': int(time.time())
            })
            logging.info("[bridge] task [%s] join queue." % str(task['uuid']))
            self._tasks_queue.put(task['uuid'], block=True)

    def run(self) -> None:
        logging.info("[bridge] enter main loop.")
        self._inner_worker.start()
        while self._is_working.get():
            task_uuid = self._tasks_queue.get(block=True)
            logging.info("[bridge] start work [%s]" % str(task_uuid))
            self._tasks_infos_v2[0]['beg'] = int(time.time())
            os.system(self._tasks_infos_v2[0]['arg']['command'])
            with self._task_locker:
                del self._tasks_infos_v2[0]

    _last_alarm = 0

    def _daemon(self) -> None:
        logging.info("[daemon] alarm checking thread start. alarm tolerance: %d minute." % __timeout_alarm__)
        while self._is_working.get():
            time.sleep(2)
            self._alarm()

    def _alarm(self):
        now = int(time.time())
        max_long = __timeout_alarm__ * 60
        count = 0
        for task_if in self._tasks_infos_v2:
            if now - task_if['add'] >= max_long:
                count += 1
        if count >= 1:
            self.notify(count)

    def notify(self, n: int):
        now = int(time.time())
        if self._last_alarm != 0 and now - self._last_alarm > __alarm_gap__ * 60 or self._last_alarm == 0:
            logging.info("\033[31;1m[alarm] %d task beyond %dmin!\033[0m" % (n, __timeout_alarm__))
            self._last_alarm = now


class TasksManager(RequestHandler):
    def get(self):
        try:
            resp = _tasks_json
        except Exception as e:
            err = "unknown error - %s" % str(e)
            logging.error(err)
            resp = {"error": err}
        self.write(resp)

    def post(self):
        try:
            global _tasks_json
            req = json.loads(self.request.body.decode(encoding='UTF-8'))
            if json.dumps(req, sort_keys=True) != json.dumps(_tasks_json, sort_keys=True):
                _tasks_json = req
            Starter.register()
            Starter.serialize(__serialization__)
            resp = {"sucess": True}
        except Exception as e:
            err = "[manager] change tasks config failed - %s" % str(e)
            logging.error(err)
            resp = {"error": err}
        self.write(resp)


class CronJobHandler(RequestHandler):
    def post(self):
        try:
            req = json.loads(self.request.body.decode(encoding='UTF-8'))
            if self.request.remote_ip != "127.0.0.1":
                self.write({"error": "No permission!"})
                return
            logging.info("[ CronJob API ] request: {}".format(json.dumps(req, ensure_ascii=False)))
            uuid = req['uuid']
            if 'token' not in req:
                token = None
            else:
                token = req['token']
            tasks = _tasks_json['tasks']
            task = None
            for every_task in tasks:
                if every_task['uuid'] == uuid:
                    task = every_task
            if task is not None:
                _default_global_context.push_task(task['bridge'], task)
            resp = {"success": True}
        except Exception as e:
            err = "http error: %s" % str(e)
            logging.error(err)
            resp = {"error": err}
        self.write(resp)


class MicroServer:
    def __init__(self):
        self.urls = [
            (r"/cron/trigger", CronJobHandler),
            (r"/tasks/manage", TasksManager),
            (r'^/(.*?)$', StaticFileHandler, {
                "path": os.path.join(os.path.dirname(__serialization__), "public"),
                "default_filename": "index.htm"}),
        ]

    def start(self):
        settings = {
            'template_path': os.path.dirname(__serialization__) + "/public",
            'static_path': os.path.dirname(__serialization__) + "/public",
        }
        app = Application(self.urls, **settings)
        server = HTTPServer(app)
        port = int("HTTP_PORT")
        server.listen(port)
        logging.info("http server start, listen port : {}".format(port))
        IOLoop.current().start()


class GlobalContext:
    _bridges = []

    def init(self):
        for i in range(__parallel_number__):
            self._bridges.append(SinglePlankBridge())
        global _default_global_context
        _default_global_context = self
        return self

    def push_task(self, bridge_id, task: dict):
        if bridge_id > len(self._bridges):
            logging.error("[bridge] bridge index out of limit!")
        self._bridges[bridge_id - 1].go(task)

    def start(self):
        [bridge.start() for bridge in self._bridges]
        return self


if __name__ == '__main__':
    prepare_logging()
    Starter.deserialize(__serialization__)
    Starter.register()
    GlobalContext().init().start()
    MicroServer().start()
