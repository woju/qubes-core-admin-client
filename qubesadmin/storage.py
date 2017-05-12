# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2017 Marek Marczykowski-Górecki
#                               <marmarek@invisiblethingslab.com>
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
# with this program; if not, see <http://www.gnu.org/licenses/>.

'''Storage subsystem.'''

class Volume(object):
    '''Storage volume.'''
    def __init__(self, app, pool=None, vid=None, vm=None, vm_name=None):
        '''Construct a Volume object.

        Volume may be identified using pool+vid, or vm+vm_name. Either of
        those argument pairs must be given.

        :param Qubes app: application instance
        :param str pool: pool name
        :param str vid: volume id (within pool)
        :param str vm: owner VM name
        :param str vm_name: name within owning VM (like 'private', 'root' etc)
        '''
        self.app = app
        if pool is None and vm is None:
            raise ValueError('Either pool or vm must be given')
        if pool is not None and vid is None:
            raise ValueError('If pool is given, vid must be too.')
        if vm is not None and vm_name is None:
            raise ValueError('If vm is given, vm_name must be too.')
        self._pool = pool
        self._vid = vid
        self._vm = vm
        self._vm_name = vm_name
        self._info = None

    def _qubesd_call(self, func_name, payload=None):
        '''Make a call to qubesd regarding this volume

        :param str func_name: API function name, like `Info` or `Resize`
        :param bytes payload: Payload to send.
        '''
        if self._vm is not None:
            method = 'admin.vm.volume.' + func_name
            dest = self._vm
            arg = self._vm_name
        else:
            method = 'admin.pool.volume.' + func_name
            dest = 'dom0'
            arg = self._pool
            if payload is not None:
                payload = self._vid.encode('ascii') + b' ' + payload
            else:
                payload = self._vid.encode('ascii')
        return self.app.qubesd_call(dest, method, arg, payload)

    def _fetch_info(self, force=True):
        '''Fetch volume properties

        Populate self._info dict

        :param bool force: refresh self._info, even if already populated.
        '''
        if not force and self._info is not None:
            return
        info = self._qubesd_call('Info')
        info = info.decode('ascii')
        self._info = dict([line.split('=', 1) for line in info.splitlines()])

    def __eq__(self, other):
        if isinstance(other, Volume):
            return self.pool == other.pool and self.vid == other.vid
        return NotImplemented

    @property
    def pool(self):
        '''Storage volume pool name.'''
        if self._pool is not None:
            return self._pool
        self._fetch_info()
        return str(self._info['pool'])

    @property
    def vid(self):
        '''Storage volume id, unique within given pool.'''
        if self._vid is not None:
            return self._vid
        self._fetch_info()
        return str(self._info['vid'])

    @property
    def size(self):
        '''Size of volume, in bytes.'''
        self._fetch_info(True)
        return int(self._info['size'])

    @property
    def usage(self):
        '''Used volume space, in bytes.'''
        self._fetch_info(True)
        return int(self._info['usage'])

    @property
    def rw(self):
        '''True if volume is read-write.'''
        self._fetch_info()
        return self._info['rw'] == 'True'

    @property
    def snap_on_start(self):
        '''Create a snapshot from source on VM start.'''
        self._fetch_info()
        return self._info['snap_on_start'] == 'True'

    @property
    def save_on_stop(self):
        '''Commit changes to original volume on VM stop.'''
        self._fetch_info()
        return self._info['save_on_stop'] == 'True'

    @property
    def source(self):
        '''Volume ID of source volume (for :py:attr:`snap_on_start`).

        If None, this volume itself will be used.
        '''
        self._fetch_info()
        if self._info['source']:
            return self._info['source']
        return None

    @property
    def internal(self):
        '''If `True` volume is hidden when qvm-block is used'''
        self._fetch_info()
        return self._info['internal'] == 'True'

    @property
    def revisions_to_keep(self):
        '''Number of revisions to keep around'''
        self._fetch_info()
        return int(self._info['revisions_to_keep'])

    def resize(self, size):
        '''Resize volume.

        Currently only extending is supported.

        :param int size: new size in bytes.
        '''
        self._qubesd_call('Resize', str(size).encode('ascii'))

    @property
    def revisions(self):
        ''' Returns iterable containing revision identifiers'''
        revisions = self._qubesd_call('ListSnapshots')
        return revisions.decode('ascii').splitlines()

    def revert(self, revision):
        ''' Revert volume to previous revision

        :param str revision: Revision identifier to revert to
        '''
        if not isinstance(revision, str):
            raise TypeError('revision must be a str')
        self._qubesd_call('Revert', revision.encode('ascii'))


class Pool(object):
    ''' A Pool is used to manage different kind of volumes (File
        based/LVM/Btrfs/...).
    '''
    def __init__(self, app, name=None):
        ''' Initialize storage pool wrapper

        :param app: Qubes() object
        :param name: name of the pool
        '''
        self.app = app
        self.name = name
        self._config = None

    def __str__(self):
        return self.name

    def __eq__(self, other):
        if isinstance(other, Pool):
            return self.name == other.name
        elif isinstance(other, str):
            return self.name == other
        return NotImplemented

    def __lt__(self, other):
        if isinstance(other, Pool):
            return self.name < other.name
        return NotImplemented

    @property
    def config(self):
        ''' Storage pool config '''
        if self._config is None:
            pool_info_data = self.app.qubesd_call(
                'dom0', 'admin.pool.Info', self.name, None)
            pool_info_data = pool_info_data.decode('utf-8')
            assert pool_info_data.endswith('\n')
            pool_info_data = pool_info_data[:-1]
            self._config = dict(
                l.split('=', 1) for l in pool_info_data.splitlines())
        return self._config

    @property
    def driver(self):
        ''' Storage pool driver '''
        return self.config['driver']

    @property
    def volumes(self):
        ''' Volumes managed by this pool '''
        volumes_data = self.app.qubesd_call(
            'dom0', 'admin.pool.volume.List', self.name, None)
        assert volumes_data.endswith(b'\n')
        volumes_data = volumes_data[:-1].decode('ascii')
        for vid in volumes_data.splitlines():
            yield Volume(self.app, self.name, vid)
