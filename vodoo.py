#!/usr/bin/env python

# TODO:
#   watch.view: to watch file when changed and update related view
#   send.scancode: to simulate code scanning

__version__ = "1.0.3"
__author__ = "Filippo Iovine <filippo.jovine@gmail.com>"
__company__ = "ME&ONLYME"

# ----------------------------------------------------------
#
# vodoo - CLI helper to support Odoo developer.
#
# Developed by Filippo Iovine
#
# 2020 - Filippo Iovine
#
# ----------------------------------------------------------

import sys
import os
from os.path import expandvars, expanduser, abspath, realpath

import time
from datetime import datetime, timedelta

import logging
from urllib.parse import urljoin

logging.basicConfig()

_logger = logging.getLogger(__name__)

try:
    import passlib.context
except ImportError:
    _logger.warning("Please install passlib package with 'pip install passlib'")
    passlib = None

try:
    import requests
except ImportError:
    _logger.warning("Please install requests package with 'pip install requests'")
    requests = None


class Colors:
    HEADER = '\033[95m'
    OK = '\033[92m'
    OKBLUE = '\033[94m'
    WARNING = '\033[93m'
    ERROR = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    ENDC = '\033[0m'


def log(s, color=None):
    try:
        if color:
            sys.stdout.write(color)

        sys.stdout.write(s)

        if color:
            sys.stdout.write(Colors.ENDC)

        sys.stdout.flush()
    except (KeyboardInterrupt, BrokenPipeError):
        # INFO: Python flushes standard streams on exit; redirect remaining output
        #       to devnull to avoid another BrokenPipeError at shutdown.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(1)


def err(s):
    log("ERROR: " + s, Colors.ERROR)


def tlog(s, color):
    log(datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] + ' > ' + s, color)


def tinf(s):
    tlog(s, Colors.OK)


def terr(s):
    tlog(s, Colors.ERROR)


def twrg(s):
    log(datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] + ' > ' + s, Colors.WARNING)


def boxed(s, title, char='-'):
    x = int((len(s) - len(title)+2) / 2)
    dx = len(s) - len(title) - 2 - x*2
    log(x*char)
    log(' ' + title.upper() + ' ')
    log((x+dx)*char + '\n')
    log(s + '\n')
    log(len(s)*char + '\n')


def str2bool(s):
    v = s.lower()
    if v not in ['true', 'false', '1', '0', 't', 'f']:
        raise ValueError("<%s> is not a valid value" % v)
    return v in ['true', '1']


HELP = """
    [OPERATION.OBJECT[.ATTRS]]                      operation command verb and its target object
    [-c|--config CONFIGFILE]                        config file
    [-d|-db|--database DATABASE]                    target odoo database
    [-du|--db-user USER]                            odoo user, defaulted to 'odoo' if not specified
    [-dp|--db-password PASSWORD]                    db password for --db-user
    [-dh|--db-host HOST]                            db host if not set then localhost
    [-h|--help]                                     shows usage information
    [-v|--version]                                  shows refreshview version info

    Operations specific arguments:
        [-m|--module MODULENAME]                    module name (mutually exclusive with --filename, -id)
        [-id ID|XML_ID]                             record id or External Odoo ID to identify Odoo object
        [-fn|--filename FILENAME]                   searches for -id into this file
        [-sid|--source-id SOURCEID]                 looks for a specific source ID in the xml -f FILENAME (content used to update -id)
        [-w|--watch]                                activates watcher to run operation when file/s change/s
        [--clear-cache]
        [-oh|--odoo-host]
        [-u|--user]                                 user login name
        [-pw|--password PASSWORD]                   new password

    Operations:
        list.fields                                 shows fields (-m)
        list.users                                  shows all available users
        list.views                                  shows all available views (-m, -id)
        set.noupdate                                updates 'noupdate' attribute to --value (-m, -id)
        set.user.password                           updates user password (-u, -pw)
        set.view.arch                               updates 'arch' content (-m, -id, -fn, -sid)
        set.view.active                             updates 'active' attribute with --value (-m, -id)
        reset.database.trial                        resets database trial info from --database
"""

EXAMPLES = """
    # Searches for 'test_view' view id in 'mymod' source file and refreshes its content.
    # When -fn is not specified, the script looks into its module folder checking its 'view' location from the Odoo DB. 
    $ vodoo update.view -d testDB -id mymod.test_view

    # Looks for 'test_view' -id in -fn source file and refreshes relative record in the odoo ir.ui.view table.
    $ vodoo update.view -d testDB -fn mymod/views/test_views.xml -id mymod.test_view

    # Looks for 'test_view' -id in -fn external source file and refreshes relative record in the odoo ir.ui.view table.
    $ vodoo update.view -d testDB -fn /samples/test_views_01.xml -id mymod.test_view

    # Refreshes all views in 'mymod' reading its location from odoo config ADDONS_PATH.
    $ vodoo update.view -d testDB -c /etc/odoo.conf -id mymod.ALL
"""


DEFAULT_CRYPT_CONTEXT = passlib and passlib.context.CryptContext(
    # kdf which can be verified by the context. The default encryption kdf is
    # the first of the list
    ['pbkdf2_sha512', 'plaintext'],
    # deprecated algorithms are still verified as usual, but ``needs_update``
    # will indicate that the stored hash should be replaced by a more recent
    # algorithm. Passlib 1.6 supports an `auto` value which deprecates any
    # algorithm but the default, but Ubuntu LTS only provides 1.5 so far.
    deprecated=['plaintext'],
)


def list_model(cr, model_op, model, argv):
    model_name = model.get('model')
    model_table = model.get('table')
    _id = argv.get('id')
    _module = argv.get('module')
    _order_by = argv.get('order-by') or 'model'

    _order_by_list = _order_by.split(',')

    _order_by_filtered = list(filter(lambda a: a in ['model', 'module', 'name'], _order_by_list))

    if len(_order_by_list) != len(_order_by_filtered):
        err('Wrong --order-by clause.\n')
        return 0, 1, 0

    _order_by = _order_by.replace('name', '%s.name' % model_table)
    _order_by = _order_by.replace('model', 'ir_model_data.model')

    qry = """
SELECT
    imd.module,
    imd.name,
    t.name,
    imd.model,
    imd.noupdate
FROM
    ir_model_data as imd,
    {model_table} as t
WHERE
    {where}
    imd.model = '{model_name}' AND
    imd.res_id = {model_table}.id
ORDER BY
    {orderby}
"""

    # INFO: 'where' clause.
    _where = ''
    if _id:
        _where = "ir_model_data.name ilike '%s' AND " % _id
    if _module:
        _where += "ir_model_data.module ilike '%s' AND " % _module

    qry = qry.format(model_name=model_name, model_table=model_table, where=_where, orderby=_order_by)
    cr.execute(qry)
    rows = cr.fetchall()
    log("{:<20} {:<50} {:<50} {:5}\n".format('module', 'id', 'name', 'noupd'))
    log(132*"-" + '\n')
    for r in rows:
        log("{:<20} {:<50} {:<50}  {:1}  \n".format(r[0][:20], r[1][:50], r[2][:50], r[4] and 'N' or ''))
    log(f'\nTotal objects: {len(rows)} (model: {model_name})\n')
    return 0, 0, 0


def list_users(cr, model_op, model, argv):
    model_name = model.get('model')
    model_table = model.get('table')
    _id = argv.get('id')
    _login = argv.get('login')
    _order_by = argv.get('order-by') or 'id'

    _order_by_list = _order_by.split(',')
    _order_by_filtered = list(filter(lambda a: a in ['id', 'login'], _order_by_list))
    if len(_order_by_list) != len(_order_by_filtered):
        err('Wrong --order-by clause.\n')
        return 0, 1, 0

    qry = """
SELECT
    id,
    active,
    login
FROM
    {model_table}
{where}
ORDER BY
    {orderby}
"""

    # INFO: 'where' clause.
    _where = ''
    if _id:
        _where = "id = %s AND " % _id
    if _login:
        _where += "login ilike %s AND " % _login
    if _where:
        _where = "WHERE " + _where

    qry = qry.format(model_table=model_table, where=_where, orderby=_order_by)
    log(qry)

    cr.execute(qry)
    rows = cr.fetchall()
    log("{:<10} {:<10} {:<25}\n".format('id', 'active', 'login'))
    log(80*"-" + '\n')
    for r in rows:
        log("{:<10} {:<10} {:<25}\n".format(r[0], r[1] and 'A' or '', r[2]))
    log('\nTotal records: %d\n' % len(rows))
    return 0, 0, 0


def update_user_password(cr, model_op, model, argv):
    if not DEFAULT_CRYPT_CONTEXT:
        err('passlib module not found!\n')
        return 0, 1, 0

    _user = argv.get('user')
    _pw = argv.get('password')

    cr.execute(
        "SELECT id from res_users where "
        "login = '%s'" % _user
    )
    r = cr.fetchone()
    if r:
        log('Updating password for <%s>.\n' % _user)

        _uid = r[0]
        ctx = DEFAULT_CRYPT_CONTEXT
        _pw = ctx.encrypt(_pw)

        assert ctx.identify(_pw) != 'plaintext'

        cr.execute('UPDATE res_users SET password = %s WHERE id = %s', (_pw, _uid))
        # TODO: trigger an invalidate cache on user model to the server.
        # self.invalidate_cache(['password'], [uid])
        return 0, 0, 1
    else:
        err('user not found!\n')
        return 0, 1, 0


from xml.etree import ElementTree as ET


def xml2arch(_module, _id, ir_model_data_name, ir_ui_view_id, ir_ui_view_type, _source_id, fn):
    nw, ne, nc = 0, 0, 0
    try:
        if not fn:
            raise FileNotFoundError

        XML = ET.parse(fn)

    except FileNotFoundError:
        terr("ERROR: file not found <%s>\n" % fn)
        twrg("> have you set xml filename with -fn?\n"
            "> or are you under addon folder where module lies?\n"
            "> or have you set -c config to use addons_path?\n")
        ne += 1
    except Exception as E:
        terr("ERROR: exception parsing file <%s>: %s\n" % (fn, E))
        ne += 1
    else:
        tinf("OK: found <%s.%s> / using file <%s>\n" % (_module, ir_model_data_name, fn))

        root = XML.getroot()

        # INFO: if --source-id then use it to look for that record snippet in the XML file.
        #       if _id is % then try to match all ids from source xml.
        rid = _source_id or ('%' not in _id and _id or ir_model_data_name)

        arch = ''
        if ir_ui_view_type in ['form', 'tree']:
            arch = root.findall(".//record[@id='%s']/field[@name='arch']" % rid)
        elif ir_ui_view_type in ['qweb']:
            arch = root.findall(".//template[@id='%s']" % rid) or \
                   root.findall(".//template[@id='%s']" % rid)
        else:
            twrg("WARNING: view <%s> not allowed.\n" % ir_ui_view_type)
            nw += 1
            return nw, ne, nc

        if not len(arch):
            terr("ERROR: no view found in the XML file <%s>. Maybe you need to install module in Odoo.\n" % fn)
            ne += 1
        # elif len(arch) > 1:
        #     log("%sERROR: there are more than one view with same id (???) in the XML file <%s>.\n" % (sprefix, fn), color=Colors.ERROR)
        #     ne += 1
        else:
            try:
                # INFO: builds the new arch xml to inject directly into target ir_ui_view.
                new_arch = b''
                for a in list(arch[0]):
                    new_arch += ET.tostring(a)

                # INFO: wraps around <data> if there are more than one children.
                #       It's mandatory else odoo crashes.
                if len(arch[0]) > 1:
                    new_arch = b'<data>' + new_arch + b'</data>'

                # INFO: decodes new_arch to make it compatible with postgres sql.
                new_arch = b'<?xml version="1.0"?>\n' + new_arch
                new_arch = new_arch.decode('utf-8').replace('"', r'\"').replace('\'', r'\'')
            except Exception as E:
                terr("%sERROR: unable refreshing new data into the view: %s\n" % E)
                ne += 1
            else:
                try:
                    # INFO: refreshes/injects new data into target view.
                    cr.execute("UPDATE ir_ui_view SET arch_db = E'%s' where id = %s" %
                               (new_arch, ir_ui_view_id))
                    tinf("OK: updated ir.ui.view ID=%s.\n" % ir_ui_view_id)
                    nc += 1
                except Exception as E:
                    terr("ERROR: exception querying postgres: %s\n" % E)
                    ne += 1

    return nw, ne, nc


def update_view(cr, model_op, model, argv):
    _module = argv.get('module')
    _id = argv.get('id')
    _source_id = argv.get('source-id')
    _filename = argv.get('filename')
    _config = argv.get('config')
    _value = argv.get('value')
    _watch = argv.get('watch')
    _clear_cache = argv.get('clear-cache')
    _odoo_host = argv.get('odoo-host', 'http://127.0.0.1:8069')
    _arch = model_op == 'arch'

    if _module and not _id:
        _id = '%'

    if not _id:
        err("missing ID or module name (use -m|--module MODULENAME or -id MODULENAME.ID)\n")
        exit(1)

    elif _filename and _config:
        err("--filename and --config are mutually exclusive\n")
        exit(1)

    # elif _filename and _id == '%':
    #     err("--filename requires unique --id.\n")
    #     exit(1)

    elif _watch and not _arch:
        err("--watch only when running set.view.arch\n")
        exit(1)

    elif _clear_cache and not _odoo_host:
        err("--clear-cache requires --odoo-host\n")
        exit(1)

    elif _filename and not _arch:
        err("--filename only when running update.view\n")
        exit(1)

    elif _source_id and not _filename:
        err("--source-id requires --filename\n")
        exit(1)

    elif not _module:
        err("\n")
        exit(1)

    # elif not arg_arch and arg_active is None and arg_noupdate is None:
    #     err("You need to set at least one of this options: --arch, --active, --noupdate.\n")
    #     fatal = 1
    # INFO: loading addons_path from config file if -c is set.

    addons_path = []
    if _config:
        try:
            import configparser as ConfigParser
        except ImportError:
            import ConfigParser

        def _normalize(path):
            return path and realpath(abspath(expanduser(expandvars(path.strip())))) or ''

        config = ConfigParser.RawConfigParser()
        try:
            config.read([_config])
            addons_path = [_normalize(x) for x in config['options']['addons_path'].split(',')]
        except IOError:
            pass
        except ConfigParser.NoSectionError:
            pass

    # INFO: searches for the module record id into ir_model_data.
    cr.execute("""SELECT
        imd.id, res_id, imd.model, type, arch_fs, imd.name, iuv.active, imd.noupdate
    FROM
        ir_ui_view as iuv, ir_model_data as imd
    WHERE
        iuv.id = imd.res_id and
        imd.module = %s and
        imd.model = %s and
        imd.name ilike %s""",
        [_module, 'ir.ui.view', _id]
    )
    rows = cr.fetchall()

    event_handlers = []
    if _watch:
        try:
            from watchdog.observers import Observer
            from watchdog.observers.api import ObservedWatch
            from watchdog.events import FileSystemEventHandler, FileModifiedEvent

            class MyHandler(FileSystemEventHandler):

                def __init__(self, module, id, model, model_data_name, view_id, view_type, source_id, filename):
                    self.last_modified = datetime.now()
                    self.nwarnings = 0
                    self.nerrors = 0
                    self.ncommits = 0
                    self.module = module
                    self.id = id
                    self.model_data_name = model_data_name
                    self.model = model
                    self.view_id = view_id
                    self.view_type = view_type
                    self.source_id = source_id
                    self.filename = filename

                def on_modified(self, event):
                    # if datetime.now() - self.last_modified >= timedelta(seconds=1):
                    if (datetime.now() - self.last_modified >= timedelta(seconds=1)):
                        if type(event) == FileModifiedEvent and \
                                event.event_type == 'modified' and \
                                self.filename == os.path.normpath(event.src_path):
                            _ne, _nw, _nc = xml2arch(
                                self.module,
                                self.id,
                                self.model_data_name,
                                self.view_id,
                                self.view_type,
                                self.source_id,
                                self.filename,
                            )
                            if self.ncommits > 0:
                                cr.connection.commit()
                                if _clear_cache:
                                    requests.get(urljoin(_odoo_host, 'clear_cache'), params={'model_name':self.model})

                            self.nerrors += _ne
                            self.nwarnings += _nw
                            self.ncommits += _nc

        except ImportError:
            err('if you want to enable watching feature, watchdog library needs to be installed (run "pip install watchdog").\n')
            return 0, 1, 0

    # INFO: checks number of occurred errors.
    nw, ne, nc = 0, 0, 0
    for row in rows:
        ir_model_data_id = row[0]
        ir_ui_view_id = row[1]
        ir_ui_view_model = row[2]
        ir_ui_view_type = row[3]
        ir_ui_view_arch_fs = row[4]
        ir_model_data_name = row[5]
        ir_ui_view_active = row[6]
        ir_model_data_noupdate = row[7]

        # INFO: updates new data into target view.
        if model_op == 'active':
            try:
                log("> found: <%s.%s> / active: %s -> %s\n" % (_module, ir_model_data_name, ir_ui_view_active, str2bool(_value)))
                cr.execute("UPDATE ir_ui_view SET active = %s where id = %s" %
                           (str2bool(_value), ir_ui_view_id))
                nc += 1
            except Exception as E:
                err("exception querying postgres: %s\n" % E)
                ne += 1

        elif model_op == 'noupdate':
            try:
                log("> found: <%s.%s> / noupdate: %s -> %s\n" % (_module, ir_model_data_name, ir_model_data_noupdate, str2bool(_value)))
                cr.execute("UPDATE ir_model_data SET noupdate = %s where id = %s" %
                           (str2bool(_value), ir_model_data_id))
                nc += 1
            except Exception as E:
                err("exception querying postgres: %s\n" % E)
                ne += 1

        # INFO: defaults to 'arch'.
        else:
            fn = False
            if addons_path:
                # INFO: Tries to look for the module thru addons_path.
                #       This is when --config has been set.
                for pt in addons_path:
                    fn = os.path.join(pt, ir_ui_view_arch_fs)
                    if os.path.exists(fn):
                        break
                    fn = False
            else:
                # INFO: if --filename option is set then use it to specify XML filename.
                #       Second option is to use directly actual folder + ir_ui_view.arch_fs.
                fn = _filename or ir_ui_view_arch_fs

            if _watch:
                event_handlers += [MyHandler(
                    _module,
                    _id,
                    ir_ui_view_model,
                    ir_model_data_name,
                    ir_ui_view_id,
                    ir_ui_view_type,
                    _source_id,
                    os.path.normpath(fn),
                )]
            else:
                nw, ne, nc = xml2arch(_module, _id, ir_model_data_name, ir_ui_view_id, ir_ui_view_type, _source_id, fn)

    if rows and _watch:
        if len(event_handlers) > 0:

            observer = Observer()
            for e in event_handlers:
                observer.schedule(e, path=os.path.dirname(e.filename), recursive=False)
                # observer.add_handler_for_watch(event_handler, ObservedWatch(os.path.dirname(fn), False))

            observer.start()
            try:
                log("Press CTRL+C to interrupt the watching.\n")
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                observer.stop()
                observer.join()

            nwarnings, nerrors, ncommits = 0, 0, 0
            for e in event_handlers:
                nwarnings += e.nwarnings
                nerrors += e.nerrors
                ncommits += e.ncommits
            log('\nWarnings: %d\n' % nwarnings, color=Colors.WARNING)
            log('Errors: %d\n' % nerrors, color=Colors.ERROR)
            log('Commits: %d\n' % ncommits, color=Colors.OK)

            # INFO: voids nerrors and ncommits to avoid committing when returning from this call.
            nc = 0

    if not rows:
        err("ID/s not found in Odoo ir_model_data.\n")
        ne = 1

    return nw, ne, nc


def set_value(cr, model_op, model, argv):
    model_name = model.get('model')
    model_table = model.get('table')
    _module = argv.get('module')
    _id = argv.get('id')
    value = argv.get('value')

    if not _id:
        err("missing ID (-id ID|XML_ID)\n")
        exit(1)

    # INFO: searches for the module record id into ir_model_data.
    cr.execute("""SELECT id, name, res_id, model, noupdate
        FROM ir_model_data as imd
        WHERE module = %s AND name = %s""",
        [_module, _id],
    )
    rows = cr.fetchall()

    # INFO: checks number of occurred errors.
    ne, nc = 0, 0
    for row in rows:
        d_id, d_name, d_res_id, d_model, d_noupdate = row

        try:
            if model_op == 'active':
                if d_model != model_name:
                    err("model mismatch: %s != %s\n" % (d_model, model_name))
                    ne += 1
                    continue
                _value = str2bool(value)
                log(f"Setting 'active' to {str(_value)} for {_module}.{_id}\n")
                cr.execute(f"UPDATE {model_table} SET active = %s WHERE id = %s", [_value, d_res_id])
                nc += 1
            else:
                _value = str2bool(value)
                log("> found: <%s.%s> / noupdate: %s -> %s\n" % (_module, d_name, d_noupdate, str(_value)))
                cr.execute("UPDATE ir_model_data SET noupdate = %s WHERE id = %s", [_value, d_id])
                nc += 1
        except Exception as E:
            err("exception querying postgres: %s\n" % E)
            ne += 1

    if not rows:
        err("ID not found in Odoo ir_model_data.\n")
        ne = 1

    return 0, ne, nc


def reset_database_trial(cr, model_op, model, argv):
    _db = argv.get('database')

    log('Resetting trial for database <%s>.\n' % _db)
    cr.execute("DELETE FROM ir_config_parameter WHERE key = 'database.expiration_date'")

    return 0, 0, 1


# *************************************
# INFO: COMMANDS METADATA
# *************************************

CMDS = {
    'list': {
        'fields': {
            'model': 'ir.model.fields',
            'table': 'ir_model_fields',
            'requires': ['database', 'module'],
            'call': list_model,
        },
        'users': {
            'model': 'res.users',
            'table': 'res_users',
            'requires': ['database'],
            'call': list_users,
        },
        'view': {
            'alias': 'list.views',
            'requires': ['id'],
        },
        'views': {
            'model': 'ir.ui.view',
            'table': 'ir_ui_view',
            'requires': ['database', 'module'],
            'call': list_model,
        },
    },
    'reset': {
        'database': {
            'trial': {
                'call': reset_database_trial,
                'requires': ['database'],
            },
        },
    },
    'set': {
        'user': {
            'password': {
                'warning': "Be sure there is no overridden or inherited auth flows in your Odoo code",
                'confirmation': True,
                'requires': ['database', 'user', 'password'],
                'call': update_user_password,
            }
        },
        'view': {
            'active': {
                'model': 'ir.ui.view',
                'table': 'ir_ui_view',
                'requires': ['database', 'value'],
                'call': set_value,
            },
            'arch': {
                'model': 'ir.ui.view',
                'table': 'ir_ui_view',
                'requires': ['database'],
                'call': update_view,
            },
            'noupdate': {
                'model': 'ir.model.data',
                'table': 'ir_model_data',
                'requires': ['database', 'value'],
                'call': set_value,
            },
        },
    },
    'show': {
        'users': {
            'alias': 'list.users'
        },
    },
}


# *************************************


if __name__ == '__main__':

    log('\n')

    # INFO: shows script and odoo version info.
    def show_version():
        try:
            import odoo

            # INFO: trick getting odoo version without loading the whole odoo crap.
            if isinstance(odoo.__path__, list):
                # INFO: odoo 10 and 11.
                odoo_release = os.path.join(odoo.__path__[0], 'release.py')
            else:
                # INFO: in case odo.__path__ is not a list then we are dealing with at least with odoo 12.
                odoo_release = os.path.join(odoo.__path__._path[0], 'odoo/release.py')

            # INFO: loads release file as a script to execute. This file contains only variables assignment.
            odoo_release_vars = {}
            exec(open(odoo_release).read(), None, odoo_release_vars)

            odoo_version = odoo_release_vars['version']

            vn = float(odoo_version)

            if vn < 10 or vn > 17:
                err("odoo version not supported!\n")
                exit(1)

        except ImportError:
            err("odoo framework not installed.\n")
            exit(1)

        log("Odoo CLI Helper developed by %s (%s)\n" % (__author__, __company__))
        log("Version: %s\n" % __version__)
        log("Odoo version: %s \n" % odoo_version)

    # INFO: shows script usage help info.
    def show_usage():
        log("  Usage:\n\n    vodoo [options]\n\n  Options:\n" + HELP + "\n")
        log("  Examples:\n" + EXAMPLES + "\n")

    args = sys.argv[1:]

    fatal = False
    arg_cmd = None
    arg_du, arg_dp, arg_db_host, arg_db_port = None, None, '127.0.0.1', '5432'
    argv = {}

    i, max_len = 0, len(args)

    # INFO: defaults to --help when vodoo has been launched without params.
    if not max_len:
        show_usage()
        exit(0)

    while i < max_len:

        if args[i] in ['-h', '--help']:
            show_usage()
            exit(0)

        elif args[i] in ['-v', '--version']:
            show_version()
            exit(0)

        elif args[i] in ['-c', '--config']:
            i += 1
            if i < max_len:
                argv['config'] = args[i]

        elif args[i] in ['-fn', '--filename']:
            i += 1
            if i < max_len:
                argv['filename'] = args[i]

        elif args[i] in ['-sid', '--source-id']:
            i += 1
            if i < max_len:
                argv['source-id'] = args[i]

        elif args[i] in ['-m', '--module']:
            i += 1
            if i < max_len:
                argv['module'] = args[i]

        elif args[i] in ['-ob', '--order-by']:
            i += 1
            if i < max_len:
                argv['order-by'] = args[i]

        elif args[i] in ['-id']:
            i += 1
            if i < max_len:
                id = args[i].split('.')
                if len(id) > 1:
                    argv['module'] = id[0]
                    _id = id[1]
                else:
                    _id = args[i]
                # INFO: parses wildcard placeholders.
                if _id == 'ALL':
                    _id = '%'
                else:
                    _id = _id.replace('*', '%')
                argv['id'] = _id

        elif args[i] in ['-w', '--watch']:
            argv['watch'] = True

        elif args[i] in ['--value']:
            i += 1
            if i < max_len:
                argv['value'] = args[i]

        elif args[i] in ['-u', '--user']:
            i += 1
            if i < max_len:
                argv['user'] = args[i]

        elif args[i] in ['-pw', '--password']:
            i += 1
            if i < max_len:
                argv['password'] = args[i]

        elif args[i] in ['-d', '-db', '--database']:
            i += 1
            if i < max_len:
                argv['database'] = args[i]

        elif args[i] in ['-du', '--db-user']:
            i += 1
            if i < max_len:
                arg_du = args[i]

        elif args[i] in ['-dp', '--db-password']:
            i += 1
            if i < max_len:
                arg_dp = args[i]


        elif args[i] in ['-cc', '--clear-cache']:
            argv['clear-cache'] = True

        elif args[i] in ['-dh', '--db-host']:
            i += 1
            if i < max_len:
                host = args[i].splt(':')
                arg_db_host = host[0]
                if len(host) > 1:
                    arg_db_port = host[1]

        elif args[i] in ['-oh', '--odoo-host']:
            i += 1
            if i < max_len:
                argv['odoo-host'] = args[i]

        else:

            # INFO: checks if there is an unknown argument: -???.
            if args[i][0] == '-':
                err("argument unknown <%s>.\n" % args[i])
                fatal = True
                break
            else:
                # INFO: if there is no argument prefix then it's an operation command.
                arg_cmd = args[i]
                # arg_cmd = args[i].split('.')
                # if len(arg_cmd) < 2:
                #     err("syntax error in command string <%s>.\n" % args[i])

        i += 1

    call_operation = None
    model_op = None
    model = None

    if not fatal:

        if not arg_cmd:
            err("operation command not specified.\n")
            fatal = 1

        elif not argv.get('database'):
            err("missing --database option.\n")
            fatal = 1

        else:
            # INFO: function to check needed arguments related to the model/object.
            def check_needed_args(need):
                for a in need:
                    if a not in argv:
                        err('Missing argument <--%s>.\n' % a)
                        return True
                return False

            def arg2cmd(cmd):
                cmds = cmd.split('.')
                return cmds[0], (len(cmds) > 1) and cmds[1] or None, (len(cmds) > 2) and cmds[2] or None

            cmd, cmd_model, cmd_object = arg2cmd(arg_cmd)
            model = CMDS.get(cmd, {}).get(cmd_model, {})
            model = model.get(cmd_object, model)
            model_op = cmd_object or cmd_model

            if isinstance(model, dict):
                if model.get('alias'):
                    cmd, cmd_model, cmd_object = arg2cmd(model.get('alias'))
                    alias_model = CMDS.get(cmd, {}).get(cmd_model, {})
                    alias_model.get("requires", []).extend(model.get("requires"))
                    model = alias_model

                call_operation = model.get('call')
                fatal = model.get('requires') and check_needed_args(model.get('requires'))

            if not call_operation:
                err("operation command <%s> unknown.\n" % arg_cmd)
                fatal = 1

    # INFO: no fatal errors occurred.
    if call_operation and not fatal:

        # INFO: suppresses warning on import psycopg2
        import warnings

        warnings.filterwarnings("ignore")

        try:
            import psycopg2
        except ImportError:
            err('psycopg2 library not installed.\n')
            exit(1)

        try:
            conn = psycopg2.connect("dbname='%s' user='%s' host='%s' port='%s' password='%s'" %
                                    (argv['database'], arg_du or 'odoo', arg_db_host, arg_db_port, arg_dp))
            cr = conn.cursor()
            try:
                nwarings, nerrors, ncommits = call_operation(cr, model_op, model, argv)
            except Exception as E:
                err("exception when running command <%s>: %s\n" % (arg_cmd, E))
            else:
                log('\n')
                if nerrors:
                    err("some errors occurred (%d)!\n" % nerrors)
                elif ncommits > 0:
                    # INFO: checks if a 'warning' message exists in the model of the command and in case displays that.
                    warning = model.get('warning')
                    if warning:
                        boxed(warning, 'warning')

                    # INFO: checks if a 'confirmation' request exists in the model of the command and in case displays that.
                    confirm = model.get('confirmation')
                    confirm = (confirm and input('\nConfirm? [Y/N] ').lower() in ('y', 'yes')) or (not confirm)
                    if confirm:
                        log("\nOK: changes committed for %d record/s!\n" % ncommits)
                        conn.commit()
                    else:
                        log("\nChanges aborted!\n")

                    cr.close()
        except Exception as E:
            err("exception when connecting to the database: %s\n" % E)

    exit(fatal)
