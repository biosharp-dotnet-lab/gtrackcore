from abc import abstractmethod, ABCMeta
import os

import tables
from tables.exceptions import ClosedFileError
import gtrackcore.preprocess

from gtrackcore.third_party.portalocker import portalocker
from gtrackcore.util.CommonConstants import GTRACKCORE_FORMAT_SUFFIX
from gtrackcore.util.CommonFunctions import convert_to_natural_naming
from gtrackcore.util.CustomExceptions import DBNotOpenError, DBNotExistError

class Database(object):
    __metaclass__ = ABCMeta

    def __init__(self, h5_filename):
        self._h5_filename = h5_filename
        self._db_name = h5_filename.split(os.sep)[-1][:-len(GTRACKCORE_FORMAT_SUFFIX)]
        self._h5_file = None
        self._cached_nodes = {}

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @abstractmethod
    def open(self, mode='r', lock_type=portalocker.LOCK_SH):
        try:
            self._h5_file = tables.open_file(self._h5_filename, mode=mode, title=self._db_name)
        except IOError, e:
            raise DBNotExistError(e)

        portalocker.lock(self._h5_file, lock_type)

    def close(self):
        self._cached_nodes = {}
        portalocker.unlock(self._h5_file)
        self._h5_file.close()

    def table_exists(self, node_names):
        table_path = self._get_node_path(node_names)
        try:
            self._h5_file.get_node(table_path)
            return True
        except tables.group.NoSuchNodeError:
            return False

    def get_table(self, node_names):
        return self.get_node(node_names)

    def get_node(self, node_names):
        node_path = self._get_node_path(node_names)
        if node_path in self._cached_nodes:
            return self._cached_nodes[node_path]
        try:
            node = self._h5_file.get_node(node_path)
            self._cached_nodes[node_path] = node
            return node
        except tables.group.NoSuchNodeError:
            return None

    def copy_node(self, node, target_node=None, recursive=True):
        self._h5_file.copy_node(node, newparent=target_node, recursive=recursive)

    def _get_node_path(self, node_names):
        return '/%s' % ('/'.join(node_names))


class DatabaseWriter(Database):

    def __init__(self, h5_filename):
        super(DatabaseWriter, self).__init__(h5_filename)
        self._flush_counter = 0

    def open(self):
        super(DatabaseWriter, self).open(mode='a', lock_type=portalocker.LOCK_EX)

    def create_table(self, node_names, table_description, expectedrows):
        table_name = node_names[-1]
        group = self._create_groups(node_names[:-1])

        try:
            table = self._h5_file.create_table(group, table_name,
                                               table_description, table_name,
                                               expectedrows=expectedrows)
        except ClosedFileError, e:
            raise DBNotOpenError(e)

        return table

    def remove_table(self, node_names):
        table_name = node_names[-1]
        group = self.get_node(node_names[:-1])
        self._h5_file.remove_node(group, table_name)

    def _create_groups(self, node_names):
        group = self.get_node(node_names)
        if group is None:
            group = self._h5_file.create_group(self._h5_file.root, node_names[0], node_names[0])

            for node_name in node_names[1:]:
                group = self._h5_file.create_group(group, node_name, node_name)

        return group


class DatabaseReader(Database):

    def __new__(cls, h5_filename):
        if not hasattr(cls, '_db_readers'):
            cls._db_readers = {}

        try:
            return cls._db_readers[h5_filename]
        except KeyError:
            new_db_readers = object.__new__(cls, h5_filename)
            cls._db_readers[h5_filename] = new_db_readers
            return new_db_readers

    def __init__(self, h5_filename):
        if not hasattr(self, '_h5_file'):
            super(DatabaseReader, self).__init__(h5_filename)

    def open(self):
        if self._h5_file is None or not self._h5_file.isopen:
            super(DatabaseReader, self).open(mode='r', lock_type=portalocker.LOCK_SH)

    def close(self):
        if gtrackcore.preprocess.is_preprocessing:
            super(DatabaseReader, self).close()
