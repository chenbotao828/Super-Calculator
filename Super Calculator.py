from __future__ import division

import sys
import re
import math
import random
from decimal import *
import datetime

import sublime
import sublime_plugin


def str_time2delta(str_time):
    regex = re.compile(
        r'((?P<days>\d+?)d)?((?P<hours>\d+?)h)?((?P<minutes>\d+?)m)?((?P<seconds>\d+?)s)?')
    parts = regex.match(str_time).groups()
    if parts:
        d = parts[1]
        h = parts[3]
        m = parts[5]
        s = parts[7]
        total_seconds = 0
        if d:
            total_seconds += int(d) * 86400
        if h:
            total_seconds += int(h) * 3600
        if m:
            total_seconds += int(m) * 60
        if s:
            total_seconds += int(s)
        days = total_seconds // 86400
        seconds = total_seconds % 86400
        return datetime.timedelta(days, seconds)
    else:
        return None


def delta2str_time(delta):
    total_seconds = delta.total_seconds()
    d = total_seconds // 86400
    h = total_seconds % 86400 // 3600
    m = total_seconds % 86400 % 3600 // 60
    s = total_seconds % 86400 % 3600 % 60
    ret = ''
    if d > 0:
        ret += "{}d".format(int(d))
    if h > 0:
        ret += "{}h".format(int(h))
    if m > 0:
        ret += "{}m".format(int(m))
    ret += "{}s".format(int(s))
    return ret


def str_time2dt(str_time):
    dt = datetime.datetime.strptime(str_time, "%Y-%m-%d %H:%M:%S")
    return dt


def dt2str_time(dt):
    str_time = dt.strftime("%Y-%m-%d %H:%M:%S")
    return str_time


class SuperCalculatorCommand(sublime_plugin.TextCommand):

    def __init__(self, view):
        self.view = view
        self.settings = sublime.load_settings(
            "Super Calculator.sublime-settings")
        self.callables = {}
        self.constants = {}
        for lib in (random, math):
            for key in dir(lib):
                attr = getattr(lib, key)
                if key[0] != '_':
                    if callable(attr):
                        self.callables[key] = attr
                    else:
                        self.constants[key] = attr
                        self.constants[key.upper()] = attr

        def Start(str_time):
            st_dt = str_time2dt(str_time)
            et_dt = datetime.datetime.now()
            du_dt = et_dt - st_dt
            et = dt2str_time(et_dt)
            du = delta2str_time(du_dt)
            return "End(\"{et}, {du}\")".format(du=du, et=et)

        self.callables['Start'] = Start

        def End(strs):
            et_str = strs.split(',')[0].strip()
            du_str = strs.split(',')[1].strip()
            et_dt = str_time2dt(et_str)
            du_delta = str_time2delta(du_str)
            st_dt = et_dt - du_delta
            st_str = dt2str_time(st_dt)
            return "Start(\"{st_str}\")".format(st_str=st_str)

        self.callables['End'] = End

        def Doing(strs):
            st_str = strs.split(',')[0].strip()
            du_str = strs.split(',')[1].strip()
            et_dt = datetime.datetime.now()
            tt_delta = str_time2delta(du_str) + (et_dt - str_time2dt(st_str))
            return "Pause(\"{}\")".format(delta2str_time(tt_delta))

        self.callables['Doing'] = Doing

        def Pause(du_str):
            st_dt = datetime.datetime.now()
            return "Doing(\"{st_str}, {du_str}\")".format(
                st_str=dt2str_time(st_dt), du_str=du_str)

        self.callables['Pause'] = Pause

        def average(nums):
            return sum(nums) / len(nums)

        self.callables['avg'] = average
        self.callables['average'] = average

        class Constant(object):
            def __init__(self, func):
                self._func = func

            def __call__(self, *args, **kwargs):
                return self._func(*args, **kwargs)

            def __repr__(self):
                return self._func()

        def init():
            now = dt2str_time(datetime.datetime.now())
            return "Start(\"{now}\"); Doing(\"{now}, 0s\");".format(now=now)
        init = Constant(init)
        self.callables['init'] = init

        def password(length=10):
            pwdchrs = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
            return ''.join(random.choice(pwdchrs) for _ in range(length))

        password = Constant(password)
        self.callables['pwd'] = password
        self.callables['password'] = password
        self.constants['pwd'] = password
        self.constants['password'] = password
        self.constants['PWD'] = password
        self.constants['PASSWORD'] = password

        allowed = '|'.join(
            [r'[-+*/%%()]'] +
            [r'\b[-+]?(\d*\.)?\d+\b'] +
            [r'\b%s\b' % c for c in self.constants.keys()] +
            [r'\b%s\s*\(' % c for c in self.callables.keys()]
        )
        self.regex = r'(%s)((%s|[ ])*(%s))?' % (allowed, allowed, allowed)
        self.dict = self.callables.copy()
        self.dict.update(self.constants)

    def run(self, edit):
        result_regions = []
        exprs = []
        for region in reversed(self.view.sel()):
            # Do the replacement in reverse order, so the character offsets
            # don't get invalidated
            exprs.append((region, self.view.substr(region)))
        for region, expr in exprs:
            if expr:
                # calculate expression and replace it with the result
                try:
                    result = str(eval(expr, self.dict, {}))
                except Exception as e:
                    sublime.status_message("Error: %s" % e)
                    continue
                else:
                    # round result if decimals are found
                    if '.' in result:
                        result = round(Decimal(result),
                                       self.settings.get("round_decimals"))
                    result = str(result)
                    if self.settings.get("trim_zeros") and '.' in result:
                        result = result.strip('0').rstrip('.')
                        if result == '':
                            result = '0'
                    if result != expr:
                        self.view.replace(edit, region, result)
                        sublime.status_message(
                            "Calculated result: " + expr + "=" + result)
                    continue
            line_region = self.view.line(region)
            match_region = self.find_reverse(self.regex, region)
            if match_region:
                match = self.view.substr(match_region)
                # validate result and check if it is in the current line
                if re.match(self.regex, match) and line_region.begin() <= match_region.begin():
                    result_regions.append(match_region)
                    sublime.status_message("Calculate: " + match + "?")
        if result_regions:
            self.view.sel().clear()
            for region in result_regions:
                self.view.sel().add(region)

    def find_reverse(self, string, region):
        new_regions = (r for r in reversed(self.view.find_all(string))
                       if r.begin() < region.end())
        try:
            if sys.version_info < (3, 0, 0):
                new_region = new_regions.next()
            else:
                new_region = next(new_regions)
        except StopIteration:
            return None
        else:
            return new_region
