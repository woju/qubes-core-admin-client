# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2017 Marek Marczykowski-Górecki
#                               <marmarek@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with this program; if not, see <http://www.gnu.org/licenses/>.
import os
import shutil
import socket
import subprocess
import unittest

import multiprocessing

try:
    import unittest.mock as mock
except ImportError:
    import mock

import tempfile

import qubesadmin.tests


class TC_00_VMCollection(qubesadmin.tests.QubesTestCase):
    def test_000_list(self):
        self.app.expected_calls[('dom0', 'admin.vm.List', None, None)] = \
            b'0\x00test-vm class=AppVM state=Running\n'
        self.assertEqual(
            list(self.app.domains.keys()),
            ['test-vm'])
        self.assertAllCalled()

    def test_001_getitem(self):
        self.app.expected_calls[('dom0', 'admin.vm.List', None, None)] = \
            b'0\x00test-vm class=AppVM state=Running\n'
        try:
            vm = self.app.domains['test-vm']
            self.assertEqual(vm.name, 'test-vm')
        except KeyError:
            self.fail('VM not found in collection')
        self.assertAllCalled()

        with self.assertRaises(KeyError):
            vm = self.app.domains['test-non-existent']
        self.assertAllCalled()

    def test_002_in(self):
        self.app.expected_calls[('dom0', 'admin.vm.List', None, None)] = \
            b'0\x00test-vm class=AppVM state=Running\n'
        self.assertIn('test-vm', self.app.domains)
        self.assertAllCalled()

        self.assertNotIn('test-non-existent', self.app.domains)
        self.assertAllCalled()

    def test_003_iter(self):
        self.app.expected_calls[('dom0', 'admin.vm.List', None, None)] = \
            b'0\x00test-vm class=AppVM state=Running\n'
        self.assertEqual([vm.name for vm in self.app.domains], ['test-vm'])
        self.assertAllCalled()

    def test_004_delitem(self):
        self.app.expected_calls[('test-vm', 'admin.vm.Remove', None, None)] = \
            b'0\x00'
        del self.app.domains['test-vm']
        self.assertAllCalled()


class TC_10_QubesBase(qubesadmin.tests.QubesTestCase):
    def test_010_new_simple(self):
        self.app.expected_calls[('dom0', 'admin.vm.Create.AppVM', None,
                b'name=new-vm label=red')] = b'0\x00'
        self.app.expected_calls[('dom0', 'admin.vm.List', None, None)] = \
            b'0\x00new-vm class=AppVM state=Running\n'
        vm = self.app.add_new_vm('AppVM', 'new-vm', 'red')
        self.assertEqual(vm.name, 'new-vm')
        self.assertEqual(vm.__class__.__name__, 'AppVM')
        self.assertAllCalled()

    def test_011_new_template(self):
        self.app.expected_calls[('dom0', 'admin.vm.Create.TemplateVM', None,
                b'name=new-template label=red')] = b'0\x00'
        self.app.expected_calls[('dom0', 'admin.vm.List', None, None)] = \
            b'0\x00new-template class=TemplateVM state=Running\n'
        vm = self.app.add_new_vm('TemplateVM', 'new-template', 'red')
        self.assertEqual(vm.name, 'new-template')
        self.assertEqual(vm.__class__.__name__, 'TemplateVM')
        self.assertAllCalled()

    def test_012_new_template_based(self):
        self.app.expected_calls[('dom0', 'admin.vm.Create.AppVM',
            'some-template', b'name=new-vm label=red')] = b'0\x00'
        self.app.expected_calls[('dom0', 'admin.vm.List', None, None)] = \
            b'0\x00new-vm class=AppVM state=Running\n'
        vm = self.app.add_new_vm('AppVM', 'new-vm', 'red', 'some-template')
        self.assertEqual(vm.name, 'new-vm')
        self.assertEqual(vm.__class__.__name__, 'AppVM')
        self.assertAllCalled()

    def test_013_new_objects_params(self):
        self.app.expected_calls[('dom0', 'admin.vm.Create.AppVM',
            'some-template', b'name=new-vm label=red')] = b'0\x00'
        self.app.expected_calls[('dom0', 'admin.label.List', None, None)] = \
            b'0\x00red\nblue\n'
        self.app.expected_calls[('dom0', 'admin.vm.List', None, None)] = \
            b'0\x00new-vm class=AppVM state=Running\n' \
            b'some-template class=TemplateVM state=Running\n'
        vm = self.app.add_new_vm(self.app.get_vm_class('AppVM'), 'new-vm',
            self.app.get_label('red'), self.app.domains['some-template'])
        self.assertEqual(vm.name, 'new-vm')
        self.assertEqual(vm.__class__.__name__, 'AppVM')
        self.assertAllCalled()

    def test_014_new_pool(self):
        self.app.expected_calls[('dom0', 'admin.vm.CreateInPool.AppVM', None,
                b'name=new-vm label=red pool=some-pool')] = b'0\x00'
        self.app.expected_calls[('dom0', 'admin.vm.List', None, None)] = \
            b'0\x00new-vm class=AppVM state=Running\n'
        vm = self.app.add_new_vm('AppVM', 'new-vm', 'red', pool='some-pool')
        self.assertEqual(vm.name, 'new-vm')
        self.assertEqual(vm.__class__.__name__, 'AppVM')
        self.assertAllCalled()

    def test_015_new_pools(self):
        self.app.expected_calls[('dom0', 'admin.vm.CreateInPool.AppVM', None,
                b'name=new-vm label=red pool:private=some-pool '
                b'pool:volatile=other-pool')] = b'0\x00'
        self.app.expected_calls[('dom0', 'admin.vm.List', None, None)] = \
            b'0\x00new-vm class=AppVM state=Running\n'
        vm = self.app.add_new_vm('AppVM', 'new-vm', 'red',
            pools={'private': 'some-pool', 'volatile': 'other-pool'})
        self.assertEqual(vm.name, 'new-vm')
        self.assertEqual(vm.__class__.__name__, 'AppVM')
        self.assertAllCalled()

    def test_020_get_label(self):
        self.app.expected_calls[('dom0', 'admin.label.List', None, None)] = \
            b'0\x00red\nblue\n'
        label = self.app.get_label('red')
        self.assertEqual(label.name, 'red')
        self.assertAllCalled()

    def test_030_clone(self):
        self.app.expected_calls[('test-vm', 'admin.vm.Clone', None,
            b'name=new-name')] = b'0\x00'
        self.app.expected_calls[('dom0', 'admin.vm.List', None, None)] = \
            b'0\x00new-name class=AppVM state=Halted\n' \
            b'test-vm class=AppVM state=Halted\n'
        new_vm = self.app.clone_vm('test-vm', 'new-name')
        self.assertEqual(new_vm.name, 'new-name')
        self.assertAllCalled()

    def test_031_clone_object(self):
        self.app.expected_calls[('test-vm', 'admin.vm.Clone', None,
            b'name=new-name')] = b'0\x00'
        self.app.expected_calls[('dom0', 'admin.vm.List', None, None)] = \
            b'0\x00new-name class=AppVM state=Halted\n' \
            b'test-vm class=AppVM state=Halted\n'
        new_vm = self.app.clone_vm(self.app.domains['test-vm'], 'new-name')
        self.assertEqual(new_vm.name, 'new-name')
        self.assertAllCalled()

    def test_032_clone_pool(self):
        self.app.expected_calls[('test-vm', 'admin.vm.CloneInPool', None,
            b'name=new-name pool=some-pool')] = b'0\x00'
        self.app.expected_calls[('dom0', 'admin.vm.List', None, None)] = \
            b'0\x00new-name class=AppVM state=Halted\n' \
            b'test-vm class=AppVM state=Halted\n'
        new_vm = self.app.clone_vm('test-vm', 'new-name', pool='some-pool')
        self.assertEqual(new_vm.name, 'new-name')
        self.assertAllCalled()

    def test_033_clone_pools(self):
        self.app.expected_calls[('test-vm', 'admin.vm.CloneInPool', None,
            b'name=new-name pool:private=some-pool '
            b'pool:volatile=other-pool')] = b'0\x00'
        self.app.expected_calls[('dom0', 'admin.vm.List', None, None)] = \
            b'0\x00new-name class=AppVM state=Halted\n' \
            b'test-vm class=AppVM state=Halted\n'
        new_vm = self.app.clone_vm('test-vm', 'new-name',
            pools={'private': 'some-pool', 'volatile': 'other-pool'})
        self.assertEqual(new_vm.name, 'new-name')
        self.assertAllCalled()


class TC_20_QubesLocal(unittest.TestCase):
    def setUp(self):
        super(TC_20_QubesLocal, self).setUp()
        self.socket_dir = tempfile.mkdtemp()
        self.orig_sock = qubesadmin.config.QUBESD_SOCKET
        qubesadmin.config.QUBESD_SOCKET = os.path.join(self.socket_dir, 'sock')
        self.proc = None
        self.app = qubesadmin.app.QubesLocal()

    def listen_and_send(self, send_data):
        '''Listen on socket and send data in response.

        :param bytes send_data: data to send
        '''
        self.socket_pipe, child_pipe = multiprocessing.Pipe()
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(os.path.join(self.socket_dir, 'sock'))
        self.socket.listen(1)

        def worker(sock, pipe, send_data_):
            conn, addr = sock.accept()
            pipe.send(conn.makefile('rb').read())
            conn.sendall(send_data_)
            conn.close()
        self.proc = multiprocessing.Process(target=worker,
            args=(self.socket, child_pipe, send_data))
        self.proc.start()
        self.socket.close()

    def get_request(self):
        '''Get request sent to "qubesd" mock'''
        return self.socket_pipe.recv()

    def tearDown(self):
        qubesadmin.config.QUBESD_SOCKET = self.orig_sock
        if self.proc is not None:
            try:
                self.proc.terminate()
            except OSError:
                pass
        shutil.rmtree(self.socket_dir)
        super(TC_20_QubesLocal, self).tearDown()

    def test_000_qubesd_call(self):
        self.listen_and_send(b'0\0')
        self.app.qubesd_call('test-vm', 'some.method', 'arg1', b'payload')
        self.assertEqual(self.get_request(),
            b'dom0\0some.method\0test-vm\0arg1\0payload')

    def test_001_qubesd_call_none_arg(self):
        self.listen_and_send(b'0\0')
        self.app.qubesd_call('test-vm', 'some.method', None, b'payload')
        self.assertEqual(self.get_request(),
            b'dom0\0some.method\0test-vm\0\0payload')

    def test_002_qubesd_call_none_payload(self):
        self.listen_and_send(b'0\0')
        self.app.qubesd_call('test-vm', 'some.method', None, None)
        self.assertEqual(self.get_request(),
            b'dom0\0some.method\0test-vm\0\0')

    def test_003_qubesd_call_payload_stream(self):
        # this should really be in setUp()...
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)

        service_path = os.path.join(tmpdir, 'test.service')
        payload_input = os.path.join(tmpdir, 'payload-input')
        with open(service_path, 'w') as f:
            f.write('#!/bin/bash\n'
                    'env > {dir}/env\n'
                    'echo "$@" > {dir}/args\n'
                    'cat > {dir}/payload\n'
                    'echo -en \'0\\0return-value\'\n'.format(dir=tmpdir))
        os.chmod(service_path, 0o755)
        with open(payload_input, 'w+') as payload_file:
            payload_file.write('some payload\n')
            payload_file.seek(0)
            with mock.patch('qubesadmin.config.QREXEC_SERVICES_DIR',
                    tmpdir):
                value = self.app.qubesd_call('test-vm', 'test.service',
                    'some-arg', payload_stream=payload_file)
        self.assertEqual(value, b'return-value')
        self.assertTrue(os.path.exists(tmpdir + '/env'))
        with open(tmpdir + '/env') as env:
            self.assertIn('QREXEC_REMOTE_DOMAIN=dom0\n', env)
            self.assertIn('QREXEC_REQUESTED_TARGET=test-vm\n', env)
        self.assertTrue(os.path.exists(tmpdir + '/args'))
        with open(tmpdir + '/args') as args:
            self.assertEqual(args.read(), 'some-arg\n')
        self.assertTrue(os.path.exists(tmpdir + '/payload'))
        with open(tmpdir + '/payload') as payload:
            self.assertEqual(payload.read(), 'some payload\n')

    def test_004_qubesd_call_payload_stream_proc(self):
        # this should really be in setUp()...
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)

        service_path = os.path.join(tmpdir, 'test.service')
        echo = subprocess.Popen(['echo', 'some payload'],
            stdout=subprocess.PIPE)
        with open(service_path, 'w') as f:
            f.write('#!/bin/bash\n'
                    'env > {dir}/env\n'
                    'echo "$@" > {dir}/args\n'
                    'cat > {dir}/payload\n'
                    'echo -en \'0\\0return-value\'\n'.format(dir=tmpdir))
        os.chmod(service_path, 0o755)
        with mock.patch('qubesadmin.config.QREXEC_SERVICES_DIR',
                tmpdir):
            value = self.app.qubesd_call('test-vm', 'test.service',
                'some-arg', payload_stream=echo.stdout)
        echo.stdout.close()
        self.assertEqual(value, b'return-value')
        self.assertTrue(os.path.exists(tmpdir + '/env'))
        with open(tmpdir + '/env') as env:
            self.assertIn('QREXEC_REMOTE_DOMAIN=dom0\n', env)
            self.assertIn('QREXEC_REQUESTED_TARGET=test-vm\n', env)
        self.assertTrue(os.path.exists(tmpdir + '/args'))
        with open(tmpdir + '/args') as args:
            self.assertEqual(args.read(), 'some-arg\n')
        self.assertTrue(os.path.exists(tmpdir + '/payload'))
        with open(tmpdir + '/payload') as payload:
            self.assertEqual(payload.read(), 'some payload\n')

    def test_010_run_service(self):
        self.listen_and_send(b'0\0')
        with mock.patch('subprocess.Popen') as mock_proc:
            p = self.app.run_service('some-vm', 'service.name')
            mock_proc.assert_called_once_with([
                qubesadmin.config.QREXEC_CLIENT,
                '-d', 'some-vm', 'DEFAULT:QUBESRPC service.name dom0'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)

        self.assertEqual(self.get_request(),
            b'dom0\0admin.vm.Start\0some-vm\0\0')

    def test_011_run_service_filter_esc(self):
        self.listen_and_send(b'0\0')
        with mock.patch('subprocess.Popen') as mock_proc:
            p = self.app.run_service('some-vm', 'service.name', filter_esc=True)
            mock_proc.assert_called_once_with([
                qubesadmin.config.QREXEC_CLIENT,
                '-d', 'some-vm', '-t', '-T',
                'DEFAULT:QUBESRPC service.name dom0'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)

        self.assertEqual(self.get_request(),
            b'dom0\0admin.vm.Start\0some-vm\0\0')

    def test_012_run_service_user(self):
        self.listen_and_send(b'0\0')
        with mock.patch('subprocess.Popen') as mock_proc:
            p = self.app.run_service('some-vm', 'service.name', user='user')
            mock_proc.assert_called_once_with([
                qubesadmin.config.QREXEC_CLIENT,
                '-d', 'some-vm',
                'user:QUBESRPC service.name dom0'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)

        self.assertEqual(self.get_request(),
            b'dom0\0admin.vm.Start\0some-vm\0\0')

    def test_013_run_service_default_target(self):
        with self.assertRaises(ValueError):
            self.app.run_service('', 'service.name')


class TC_30_QubesRemote(unittest.TestCase):
    def setUp(self):
        super(TC_30_QubesRemote, self).setUp()
        self.proc_mock = mock.Mock()
        self.proc_mock.configure_mock(**{
            'return_value.returncode': 0
        })
        self.proc_patch = mock.patch('subprocess.Popen', self.proc_mock)
        self.proc_patch.start()
        self.app = qubesadmin.app.QubesRemote()

    def set_proc_stdout(self, send_data):
        self.proc_mock.configure_mock(**{
            'return_value.communicate.return_value': (send_data, None)
        })

    def tearDown(self):
        self.proc_patch.stop()
        super(TC_30_QubesRemote, self).tearDown()

    def test_000_qubesd_call(self):
        self.set_proc_stdout(b'0\0')
        self.app.qubesd_call('test-vm', 'some.method', 'arg1', b'payload')
        self.assertEqual(self.proc_mock.mock_calls, [
            mock.call([qubesadmin.config.QREXEC_CLIENT_VM, 'test-vm',
                'some.method+arg1'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE),
            mock.call().communicate(b'payload')
        ])

    def test_001_qubesd_call_none_arg(self):
        self.set_proc_stdout(b'0\0')
        self.app.qubesd_call('test-vm', 'some.method', None, b'payload')
        self.assertEqual(self.proc_mock.mock_calls, [
            mock.call([qubesadmin.config.QREXEC_CLIENT_VM, 'test-vm',
                'some.method'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE),
            mock.call().communicate(b'payload')
        ])

    def test_002_qubesd_call_none_payload(self):
        self.set_proc_stdout(b'0\0')
        self.app.qubesd_call('test-vm', 'some.method', None, None)
        self.assertEqual(self.proc_mock.mock_calls, [
            mock.call([qubesadmin.config.QREXEC_CLIENT_VM, 'test-vm',
                'some.method'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE),
            mock.call().communicate(None)
        ])

    def test_003_qubesd_call_payload_stream(self):
        self.set_proc_stdout(b'0\0return-value')
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir)

        payload_input = os.path.join(tmpdir, 'payload-input')
        with open(payload_input, 'w+') as payload_file:
            payload_file.write('some payload\n')
            payload_file.seek(0)

            value = self.app.qubesd_call('test-vm', 'some.method',
                'some-arg', payload_stream=payload_file)
        self.assertEqual(self.proc_mock.mock_calls, [
            mock.call([qubesadmin.config.QREXEC_CLIENT_VM, 'test-vm',
                'some.method+some-arg'],
                stdin=payload_file, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE),
            mock.call().communicate(None)
        ])
        self.assertEqual(value, b'return-value')

    def test_010_run_service(self):
        self.app.run_service('some-vm', 'service.name')
        self.proc_mock.assert_called_once_with([
            qubesadmin.config.QREXEC_CLIENT_VM,
            'some-vm', 'service.name'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

    def test_011_run_service_filter_esc(self):
        with self.assertRaises(NotImplementedError):
            p = self.app.run_service('some-vm', 'service.name', filter_esc=True)

    def test_012_run_service_user(self):
        with self.assertRaises(ValueError):
            p = self.app.run_service('some-vm', 'service.name', user='user')

    def test_013_run_service_default_target(self):
        self.app.run_service('', 'service.name')
        self.proc_mock.assert_called_once_with([
            qubesadmin.config.QREXEC_CLIENT_VM,
            '', 'service.name'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
