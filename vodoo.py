#!/usr/bin/env python

__version__ = "0.1.1"
__author__ = "Filippo Iovine <admin@bluebytech.com>"
__company__ = "BLUEBYTECH"

# ----------------------------------------------------------
#
# Odoo View Refresher - helper to quickly refresh a target view xml content.
#
# Developed by Filippo Iovine
#
# 2020 - BLUEBYTECH
#
# ----------------------------------------------------------

import sys
import os
from os.path import expandvars, expanduser, abspath, realpath

import logging

logging.basicConfig()


def log(s):
    sys.stdout.write(s)


def err(s):
    log("ERROR: " + s)


log('\n')

HELP = """
    [COMMAND]                                   operation command                                                
    [-c|--config CONFIGFILE]                    config file
    [-d|-db|--database DATABASE]                target odoo database
    [-du|--db-user USER]                        odoo user, defaulted to 'odoo' if not specified
    [-dp|--db-password PASSWORD]                db password for --db-user
    [-dh|--db-host HOST]                        db host if not set then localhost
    [-h|--help]                                 shows usage information
    [-v|--version]                              shows refreshview version info

    COMMAND:
        ur|upd-rec|update-record                update a record by its ID (ir.ui.view is the only model data updatable so far)
    arguments: 
        [-id ID|MODULENAME.ID]                  record id to update, if MODULENAME.ID then no need to specify --module
        [-m|--module MODULENAME]                used to set module name if no --filename or -id MODULENAME is not set
        [-f|--filename FILENAME]                if set then searches for -id into this file, no need of --module or -ID MODULE
        [-sid|--source-id SOURCEID]             look for source ID in the xml -f FILENAME

"""

EXAMPLES = """

    # Searches for 'test_view' view id in 'mymod' source file and refreshes its content.
    # When -f is not specified, the script looks into its module folder checking its 'view' location from the Odoo DB. 
    $ vodoo update-record -d testDB -id mymod.test_view

    # Looks for 'test_view' -id in -f source file and refreshes relative record in the odoo ir.ui.view table.
    $ vodoo update-record -d testDB -f mymod/views/test_views.xml -id mymod.test_view

    # Looks for 'test_view' -id in -f external source file and refreshes relative record in the odoo ir.ui.view table.
    $ vodoo update-record -d testDB -f /samples/test_views_01.xml -id mymod.test_view

    # Refreshes all views in 'mymod' reading its location from odoo config ADDONS_PATH.
    $ vodoo update-record -d testDB -c /etc/odoo.conf -id mymod.ALL

"""

CMD_UPDATE_RECORD = ['ur', 'upd-rec', 'update-record']

if __name__ == '__main__':

    # INFO: shows script and odoo version info.
    def show_version():
        odoo_version = None

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

            if vn < 10 or vn > 14:
                err("odoo version not supported!\n")
                exit(1)

        except ImportError:
            err("odoo framework not installed.\n")
            exit(1)

        log("Odoo View Refresher developed by %s (%s)\n" % (__author__, __company__))
        log("Version: %s\n" % __version__)
        log("Odoo version: %s \n" % odoo_version)


    # INFO: shows script usage help info.
    def show_usage():
        log("  Usage:\n\n    odoo-vr [options]\n\n  Options:\n" + HELP)
        log("  Examples:\n" + EXAMPLES)


    args = sys.argv[1:]

    fatal = False
    arg_cmd = None
    arg_c, arg_f, arg_id, arg_sid, arg_m = None, None, None, None, None
    arg_db, arg_du, arg_dp, arg_db_host, arg_db_port = None, None, None, '127.0.0.1', '5432'

    i, max_len = 0, len(args)

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
                arg_c = args[i]

        elif args[i] in ['-f', '--filename']:
            i += 1
            if i < max_len:
                arg_f = args[i]

        elif args[i] in ['-sid', '--source-id']:
            i += 1
            if i < max_len:
                arg_sid = args[i]

        elif args[i] in ['-m', '--module']:
            i += 1
            if i < max_len:
                arg_m = args[i]

        elif args[i] in ['-d', '-db', '--database']:
            i += 1
            if i < max_len:
                arg_db = args[i]

        elif args[i] in ['-du', '--db-user']:
            i += 1
            if i < max_len:
                arg_du = args[i]

        elif args[i] in ['-dp', '--db-password']:
            i += 1
            if i < max_len:
                arg_dp = args[i]

        elif args[i] in ['-dh', '--db-host']:
            i += 1
            if i < max_len:
                host = args[i].partition(':')
                arg_db_host = host[0]
                arg_db_port = host[2]

        elif args[i] in ['-id']:
            i += 1
            if i < max_len:
                dotp = args[i].find('.')
                if dotp >= 0 and dotp + 1 < len(args[i]):
                    arg_m = args[i][:dotp]
                    arg_id = args[i][dotp + 1:]
                else:
                    arg_id = args[i]

        else:

            # INFO: checks if there is an unknown argument: -???.
            if args[i][0] == '-':
                err("argument unknown <%s>.\n" % args[i])
                fatal = True
                break
            else:
                # INFO: if there is no argument prefix then it's an operation command.
                arg_cmd = args[i]

        i += 1

    if not fatal:

        if not arg_cmd:
            err("operation command not specified.\n")
            fatal = 1

        elif not arg_db:
            err("missing --database option.\n")
            fatal = 1

        elif arg_cmd in CMD_UPDATE_RECORD:
            if arg_f and arg_c:
                err("--filename and --config are mutually exclusive.\n")
                fatal = 1

            elif arg_f and arg_id == 'ALL':
                err("cannot use --filename and ALL ids feature.\n")
                fatal = 1

            elif not arg_m:
                err("missing module name (use --module or -id MODULENAME.ID).\n")
                fatal = 1

            elif not arg_id:
                err("missing record id (use -id ID|MODULENAME.ID).\n")
                fatal = 1

        else:
            err("operation command <%s> unknown.\n" % arg_cmd)
            fatal = 1

    # INFO: no fatal errors occurred.
    if not fatal:

        # INFO: suppresses warning on import psycopg2
        import warnings

        warnings.filterwarnings("ignore")

        import psycopg2

        try:
            conn = psycopg2.connect("dbname='%s' user='%s' host='%s' port='%s' password='%s'" %
                                    (arg_db, arg_du or 'odoo', arg_db_host, arg_db_port, arg_dp))
            cur = conn.cursor()

            if arg_cmd in CMD_UPDATE_RECORD:

                # INFO: loading addons_path from config file if -c is set.
                addons_path = []
                if arg_c:
                    try:
                        import configparser as ConfigParser
                    except ImportError:
                        import ConfigParser

                    def _normalize(path):
                        if not path:
                            return ''
                        return realpath(abspath(expanduser(expandvars(path.strip()))))

                    config = ConfigParser.RawConfigParser()
                    try:
                        config.read([arg_c])
                        addons_path = [_normalize(x) for x in config['options']['addons_path'].split(',')]
                    except IOError:
                        pass
                    except ConfigParser.NoSectionError:
                        pass

                if arg_id == 'ALL':
                    # INFO: searches for all module records id into ir_model_data.
                    cur.execute(
                        "SELECT res_id, arch_fs, ir_model_data.name from ir_ui_view, ir_model_data where "
                        "ir_ui_view.id = ir_model_data.res_id and "
                        "ir_model_data.module = '%s' and "
                        "ir_model_data.model = '%s'"
                        % (arg_m, 'ir.ui.view')
                    )
                    rows = cur.fetchall()
                else:
                    # INFO: searches for the module record id into ir_model_data.
                    cur.execute(
                        "SELECT res_id, arch_fs, ir_model_data.name from ir_ui_view, ir_model_data where "
                        "ir_ui_view.id = ir_model_data.res_id and "
                        "ir_model_data.module = '%s' and "
                        "ir_model_data.model = '%s' and "
                        "ir_model_data.name = '%s'"
                        % (arg_m, 'ir.ui.view', arg_id)
                    )
                    rows = cur.fetchall()

                # INFO: checks number of occured errors.
                nerror = 0
                for row in rows:
                    ir_ui_view_id = row[0]
                    ir_ui_view_arch_fs = row[1]
                    ir_model_data_name = row[2]

                    from xml.etree import ElementTree as ET

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
                        # INFO: if --filename option is set the use it to specify XML filename.
                        #       Second option is to use directly actual folder + ir_ui_view.arch_fs.
                        fn = (arg_id != 'ALL' and arg_f) or ir_ui_view_arch_fs

                    try:
                        if not fn:
                            raise FileNotFoundError

                        XML = ET.parse(fn)

                    except FileNotFoundError as NF:
                        err("file not found <%s>\n" % fn)
                        log("> have you set xml file path with -f?\n"
                            "> are you under addon folder where module lies?\n"
                            "> have you set -c config so to use addons_path?\n")
                        nerror += 1
                    except Exception as E:
                        err("exception parsing file <%s>: %s\n" % (fn, E))
                        nerror += 1
                    else:
                        log("> found: <%s.%s> / using file: <%s>\n" % (arg_m, ir_model_data_name, fn))

                        root = XML.getroot()

                        # INFO: if --source-id then use it to look for that record snippet in the XML file.
                        rid = arg_sid or (arg_id != 'ALL' and arg_id or ir_model_data_name)

                        arch = root.findall(".//record[@id='%s']/field[@name='arch']" % rid)
                        if not len(arch):
                            err("no view found in the XML file <%s>.\n" % fn)
                            nerror += 1
                        elif len(arch) > 1:
                            err("there are more than one view with same id (???) in the XML file <%s>.\n" % fn)
                            nerror += 1
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
                                err("unable refreshing new data into the view: %s" % E)
                                nerror += 1
                            else:
                                try:
                                    # INFO: refreshes/injects new data into target view.
                                    cur.execute("UPDATE ir_ui_view SET arch_db = E'%s' where id = '%s'" %
                                                (new_arch, ir_ui_view_id))
                                    conn.commit()
                                except Exception as E:
                                    err("exception querying postgres to update ir_ui_view: %s" % E)
                                    nerror += 1
                    # log("\n")

                if not rows:
                    err("ID/s not found in Odoo ir_model_data.\n")
                    nerror = 1

                cur.close()

                log("\n")
                if not nerror:
                    log("OK: record/s updated!\n")
                else:
                    err("some errors occured (%d)!\n" % nerror)

                exit(nerror > 0)

        except Exception as E:
            err("exception when connecting to the database: %s" % E)

    exit(fatal)
