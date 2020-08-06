import os
import logging
import re


_regex_gap = r' |\t'
_regex_ps = r'('
_regex_pe = r')'
_regex_minute_per = r'\*(/[0-9]+)?'
_regex_minute_multi = r'[0-9]+(,[0-9]+)*'
_regex_hour_per = _regex_minute_per
_regex_hour_multi = r'[0-9]+(-[0-9]+(/[0-9]+)?)?(,[0-9]+(-[0-9]+(/[0-9]+)?)?)*'
_regex_day_of_month_per = _regex_hour_per
_regex_day_of_month_multi = _regex_hour_multi
_regex_month_per = r'\*(/([0-9]+|[a-z]+))?'
_regex_month_multi = r'([0-9]+|[a-z]+)(-([0-9]+|[a-z]+)(/([0-9]+|[a-z]+))?)?' \
                 r'(,([0-9]+|[a-z]+)(-([0-9]+|[a-z]+)(/([0-9]+|[a-z]+))?)?)*'
_regex_day_of_week_per = _regex_month_per
_regex_day_of_week_multi = _regex_month_multi


def _regex_joint_or(regex_0, regex_1):
    return "".join([
        _regex_ps, _regex_ps, regex_0,
        _regex_pe, r'|', _regex_ps,
        regex_1, _regex_pe, _regex_pe])


def _regex_joint(regex_list):
    return _regex_ps + (_regex_pe + _regex_ps).join(regex_list) + _regex_pe


_regex_minute = _regex_joint_or(_regex_minute_per, _regex_minute_multi)
_regex_hour = _regex_joint_or(_regex_hour_per, _regex_hour_multi)
_regex_day_of_month = _regex_joint_or(_regex_day_of_month_per, _regex_day_of_month_multi)
_regex_month = _regex_joint_or(_regex_month_per, _regex_month_multi)
_regex_day_of_week = _regex_joint_or(_regex_day_of_week_per, _regex_day_of_week_multi)
_regex_whole = _regex_joint(
    [_regex_minute,
     _regex_gap, _regex_hour,
     _regex_gap, _regex_day_of_month,
     _regex_gap, _regex_month,
     _regex_gap, _regex_day_of_week])


def _match(org, pattern):
    rem = re.match(pattern, org)
    return org[rem.start(): rem.end()] == org if rem is not None else False


def extract(seqs: str):
    l_seqs = seqs.split('\t') if '\t' in seqs else seqs.split(' ')
    l_seqs = l_seqs + ['*'] * (5 - len(l_seqs))
    if not _match(" ".join(l_seqs), _regex_whole):
        raise RuntimeError("Error cron tab syntax!")
    return {
        "minute": l_seqs[0],
        "hour": l_seqs[1],
        "day_of_month": l_seqs[2],
        "month": l_seqs[3],
        "day_of_week": l_seqs[4],
    }


def _satisfy(p_task, key, **kwargs):
    return kwargs[key] == p_task[key] if key in kwargs else True


def _builder(key, **kwargs):
    return kwargs[key] if key in kwargs else '*'


def _validate(minute):
    ex = "Un-support minute cron-tab format - {}".format(minute)
    if minute.isnumeric():
        return
    if len(minute) > 1:
        if minute[0:1] == '/' and minute[1:].isnumeric():
            pass
        elif minute[0:2] == '*/' and minute[2:].isnumeric():
            pass
        else:
            if ',' in minute:
                nums = minute.split(',')
                for num in nums:
                    if not num.isnumeric():
                        raise Exception(ex)
            else:
                raise Exception(ex)


class RootCronTabDriver:
    """Here, providing a cron-tab manager class for controlling cron task.
    Because of using docker as running environment, we just use 'root' identity.
    This class provided the following basic functions:
        1. create a cron task by providing command(script argument),
           time point(minute, hour and so on);
        2. remove an exist cron task;
        3. validate whether a cron task existed in cron-tab
    The most important key function is:
        4. the class can keep synchronous with cron-tab file, to execute
           every command in time.
    """
    _tasks = {}

    _default_manage_file = "/var/spool/cron/aiyo"

    def __init__(self):
        """Loading all of tasks to core data structure(self._tasks) first!"""
        self._load_tasks()

    def has(self, script, **kwargs):
        """Judging whether exist the same cron task in cron-tab."""
        for p_task in self._tasks.values():
            if script == p_task['script'] \
                    and _satisfy(p_task, 'minute', **kwargs) \
                    and _satisfy(p_task, 'hour', **kwargs) \
                    and _satisfy(p_task, 'day_of_month', **kwargs) \
                    and _satisfy(p_task, 'month', **kwargs) \
                    and _satisfy(p_task, 'day_of_week, **kwargs'):
                return True
        return False

    def display(self):
        return [task['script'] for k, task in self._tasks.items()]

    def remove_task(self, script, regex=False, **kwargs):
        """ Remove the specific task, which given
        script and minute timer (+hour/day/month). """
        task_uuids = []
        for p_uuid, p_task in self._tasks.items():
            if _satisfy(p_task, 'minute', **kwargs) \
                    and _satisfy(p_task, 'hour', **kwargs) \
                    and _satisfy(p_task, 'day_of_month', **kwargs) \
                    and _satisfy(p_task, 'month', **kwargs) \
                    and _satisfy(p_task, 'day_of_week', **kwargs):
                if not regex and script == p_task['script']:
                    task_uuids.append(p_uuid)
                elif regex and script in p_task['script']:
                    task_uuids.append(p_uuid)
        if len(task_uuids) != 0:
            for task_uuid in task_uuids:
                del self._tasks[task_uuid]
        self._sync_tasks()

    def create_task(self, script, **kwargs):
        """Create a cron task. Validating first(whether have the
        same task, timer format and other limitation if necessary)!"""
        if self.has(script, **kwargs):
            return
        if len(kwargs) == 0:
            raise Exception("Specify at least one of "
                            "minute/hour/day_of_month/month/day_of_week!")
        _validate(kwargs['minute']) if 'minute' in kwargs else None
        task = {
            'minute': _builder('minute', **kwargs),
            'hour': _builder('hour', **kwargs),
            'day_of_month': _builder('day_of_month', **kwargs),
            'month': _builder('month', **kwargs),
            'day_of_week': _builder('day_of_week', **kwargs),
            "script": script,
        }
        self._tasks["{} {} {} {} {} {}".format(
            _builder('minute', **kwargs),
            _builder('hour', **kwargs),
            _builder('day_of_month', **kwargs),
            _builder('month', **kwargs),
            _builder('day_of_week', **kwargs), script,
        )] = task
        self._sync_tasks()

    def _sync_tasks(self):
        """Write the memory data into disk. When sync task in memory
         with disk, it will sort all of tasks."""
        p_ctx = '\n'.join([pair[0] for pair in sorted(
            self._tasks.items(), key=lambda x: x[1]['script'])]) + '\n'
        try:
            fp = open(self._default_manage_file, 'w')
            fp.write(p_ctx)
            fp.close()
        except Exception as e:
            logging.error("|EE| Sync cron-tab file failed, {}.".format(str(e)))

    def _load_tasks(self):
        """Loading all of the cron tasks from cron-tab file. If no cron-tab
        created, here, it will create the default cron-tab file first. Then,
        parsing every cron task and loading into memory."""
        open(self._default_manage_file, 'w').close() \
            if not os.path.exists(self._default_manage_file) else None
        fp = open(self._default_manage_file)
        p_ctx = fp.read()
        p_seg = p_ctx.split('\n')
        for p_line in p_seg:
            p_words = p_line.split(' ')
            p_words = [every for every in p_words if every != '']
            if len(p_words) >= 6 and p_words[0][0] != '#':
                self._tasks[' '.join(p_words)] = ({
                    'minute': p_words[0],
                    'hour': p_words[1],
                    'day_of_month': p_words[2],
                    'month': p_words[3],
                    'day_of_week': p_words[4],
                    'script': ' '.join(p_words[5:]),
                })

    def __str__(self):
        """It's convenient to output the context of cron-tab file.
        Or, in other words, to display the memory context conveniently."""
        return '\n'.join([pair[0] for pair in sorted(
            self._tasks.items(), key=lambda x: x[1]['script'])])
