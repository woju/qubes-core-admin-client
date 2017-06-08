#
# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2016  Marek Marczykowski-Górecki
#                                       <marmarek@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

''' Tool for importing rpm-installed template'''

import asyncio
import glob
import os

import shutil
import subprocess

import sys

import grp

import time

import qubesadmin
import qubesadmin.exc
import qubesadmin.tools
try:
    # pylint: disable=wrong-import-position
    import qubesadmin.events.utils
    have_events = True
except ImportError:
    have_events = False

parser = qubesadmin.tools.QubesArgumentParser(
    description='Postprocess template package')
parser.add_argument('--really', action='store_true', default=False,
    help='Really perform the action, YOU SHOULD REALLY KNOW WHAT YOU ARE DOING')
parser.add_argument('--skip-start', action='store_true',
    help='Do not start the VM - do not retrieve menu entries etc.')
parser.add_argument('--keep-source', action='store_true',
    help='Do not remove imported data')
parser.add_argument('action', choices=['post-install', 'pre-remove'],
    help='Action to perform')
parser.add_argument('name', action='store',
    help='Template name')
parser.add_argument('dir', action='store',
    help='Template directory')


def move_if_exists(source, dest_dir):
    '''Move file/directory if exists'''
    if os.path.exists(source):
        shutil.move(source, os.path.join(dest_dir, os.path.basename(source)))


def get_root_img_size(source_dir):
    '''Extract size of root.img to be imported'''
    root_path = os.path.join(source_dir, 'root.img')
    if os.path.exists(root_path + '.part.00'):
        # get just file root_size from the tar header
        p = subprocess.Popen(['tar', 'tvf', root_path + '.part.00'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        (stdout, _) = p.communicate()
        # -rw-r--r-- 0/0      1073741824 1970-01-01 01:00 root.img
        root_size = int(stdout.split()[2])
    elif os.path.exists(root_path):
        root_size = os.path.getsize(root_path)
    else:
        raise qubesadmin.exc.QubesException('root.img not found')
    return root_size


def import_root_img(vm, source_dir):
    '''Import root.img into VM object'''

    root_size = get_root_img_size(source_dir)
    vm.volumes['root'].resize(root_size)

    root_path = os.path.join(source_dir, 'root.img')
    if os.path.exists(root_path + '.part.00'):
        input_files = glob.glob(root_path + '.part.*')
        cat = subprocess.Popen(['cat'] + sorted(input_files),
            stdout=subprocess.PIPE)
        tar = subprocess.Popen(['tar', 'xSOf', '-'],
            stdin=cat.stdout,
            stdout=subprocess.PIPE)
        cat.stdout.close()
        vm.volumes['root'].import_data(stream=tar.stdout)
        if tar.wait() != 0:
            raise qubesadmin.exc.QubesException('root.img extraction failed')
        if cat.wait() != 0:
            raise qubesadmin.exc.QubesException('root.img extraction failed')
    elif os.path.exists(root_path):
        if vm.app.qubesd_connection_type == 'socket':
            # check if root.img was already overwritten, i.e. if the source
            # and destination paths are the same
            vid = vm.volumes['root'].vid
            pool = vm.app.pools[vm.volumes['root'].pool]
            if pool.driver == 'file' and root_path == os.path.join(
                    pool.config['dir_path'], vid + '.img'):
                vm.log.info('root.img already in place, do not re-import')
                return
        with open(root_path, 'rb') as root_file:
            vm.volumes['root'].import_data(stream=root_file)


def import_appmenus(vm, source_dir):
    '''Import appmenus settings into VM object (later: GUI VM)'''
    if os.getuid() == 0:
        try:
            qubes_group = grp.getgrnam('qubes')
            user = qubes_group.gr_mem[0]
            cmd_prefix = ['runuser', '-u', user, '--', 'env', 'DISPLAY=:0']
        except KeyError as e:
            vm.log.warning('Default user not found, not importing appmenus: ' +
                           str(e))
            return
    else:
        cmd_prefix = []

    # TODO: change this to qrexec calls to GUI VM, when GUI VM will be
    # implemented
    subprocess.check_call(cmd_prefix + ['qvm-appmenus',
        '--set-default-whitelist={}'.format(os.path.join(source_dir,
            'vm-whitelisted-appmenus.list')), vm.name])
    subprocess.check_call(cmd_prefix + ['qvm-appmenus',
        '--set-whitelist={}'.format(os.path.join(source_dir,
            'whitelisted-appmenus.list')), vm.name])


def post_install(args):
    '''Handle post-installation tasks'''

    app = args.app
    try:
        # reinstall
        vm = app.domains[args.name]
    except KeyError:
        if app.qubesd_connection_type == 'socket' and \
                args.dir == '/var/lib/qubes/vm-templates/' + args.name:
            # vm.create_on_disk() need to create the directory on its own,
            # move it away for from its way
            tmp_sourcedir = os.path.join('/var/lib/qubes/vm-templates',
                'tmp-' + args.name)
            shutil.move(args.dir, tmp_sourcedir)
            args.dir = tmp_sourcedir

        vm = app.add_new_vm('TemplateVM',
            name=args.name,
            label=qubesadmin.config.defaults['template_label'])

    vm.log.info('Importing data')
    import_root_img(vm, args.dir)
    import_appmenus(vm, args.dir)

    if not args.skip_start:
        # just created, so no need to save previous value - we know what it was
        vm.netvm = None
        vm.start()
        try:
            vm.run_service_for_stdio('qubes.PostInstall')
        except qubesadmin.exc.QubesVMError:
            vm.log.error('qubes.PostInstall service failed')
        vm.shutdown()
        if have_events:
            try:
                # pylint: disable=no-member
                qubesadmin.events.utils.wait_for_domain_shutdown(vm,
                    qubesadmin.config.defaults['shutdown_timeout'])
            except qubesadmin.exc.QubesVMShutdownTimeout:
                vm.kill()
            asyncio.get_event_loop().close()
        else:
            timeout = qubesadmin.config.defaults['shutdown_timeout']
            while timeout >= 0:
                if vm.is_halted():
                    break
                time.sleep(1)
                timeout -= 1
            if not vm.is_halted():
                vm.kill()

        vm.netvm = qubesadmin.DEFAULT

    return 0


def pre_remove(args):
    '''Handle pre-removal tasks'''
    app = args.app
    try:
        tpl = app.domains[args.name]
    except KeyError:
        parser.error('Qube with this name do not exist')
    for appvm in tpl.appvms:
        parser.error('Qube {} use this template'.format(appvm.name))

    del app.domains[args.name]
    return 0


def main(args=None, app=None):
    '''Main function of qvm-template-postprocess'''
    args = parser.parse_args(args, app=app)
    if not args.really:
        parser.error('Do not call this tool directly.')
    if args.action == 'post-install':
        return post_install(args)
    elif args.action == 'pre-remove':
        pre_remove(args)
    else:
        parser.error('Unknown action')
    return 0

if __name__ == '__main__':
    sys.exit(main())
