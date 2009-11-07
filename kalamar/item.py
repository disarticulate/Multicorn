# -*- coding: utf-8 -*-
# This file is part of Dyko
# Copyright © 2008-2009 Kozea
#
# This library is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Kalamar.  If not, see <http://www.gnu.org/licenses/>.

"""
Base classes to create kalamar items.

You probably want to use the Item.get_item_parser method to get the parser you
need. You may also want to inherit from one of the followings so you can write
your own parsers:
- CapsuleItem
- AtomItem

Any item parser class has to have a static attribute ``format`` set to the
format parsed, otherwise this class will be hidden to get_item_parser.

A parser class must implement the following methods:
- _custom_parse_data(self)
- _custom_serialize(self, properties)

It must have a class attribute ``format`` which is name of the parsed format.

Parser classes can define an atribute ``_keys`` listing the name of the
properties they *need* to work well.

"""

from copy import copy
from werkzeug import MultiDict, CombinedMultiDict
from cStringIO import StringIO
    
from kalamar import parser, utils

class Item(object):
    """Abstract class, base of any item parser.
    
    You can use the Item.get_item_parser static method to get automatically the
    parser you want.

    Useful tips:
    - Item acts as a defaultdict. The keys are strings and the values are
      MultiDict of python objects with default value at None.
    - _access_point: attribute where, in kalamar, is stored the item. It is
      an instance of AccessPoint.

    This class is abstract and used by AtomItem and CapsuleItem, which are
    inherited by the parsers.

    TODO: write tests and documentation

    """
    format = None

    def __init__(self, access_point, opener=StringIO, storage_properties={}):
        """Return an instance of Item.
        
        Parameters:
        - access_point: an instance of the AccessPoint class.
        - opener: a function taking no parameters and returning file-like
          object.
        - storage_properties: properties generated by the storage for this
          item.
        
        """
        self._opener = opener
        self._stream = None
        self._access_point = access_point
        self._loaded = False
        self._content_modified = False
        self._parser_modified = False
        
        self.storage_aliases = dict(access_point.storage_aliases)
        self.parser_aliases = dict(access_point.parser_aliases)
        
        self.raw_storage_properties = MultiDict(storage_properties)
        self.raw_parser_properties = MultiDict()

        self.storage_properties = AliasedMultiDict(
            self.raw_storage_properties, self.storage_aliases)
        self.parser_properties = AliasedMultiDict(
            self.raw_parser_properties, self.parser_aliases)
        
        self.raw_properties = CombinedMultiDict([
                self.raw_storage_properties, self.raw_parser_properties])
        self.properties = CombinedMultiDict([
                self.storage_properties, self.parser_properties])

        self['_content'] = ''
        self.old_storage_properties = copy(storage_properties)

    def __getitem__(self, key):
        """Return the item ``key`` property."""
        # Lazy load: load item only when needed
        if not self._loaded:
            self._parse_data()
            self._loaded = True            

        try:
            return self.properties[key]
        except KeyError:
            return None
    
    def __setitem__(self, key, value):
        """Set the item ``key`` property to ``value``."""
        # TODO: maybe use setlist/getlist attributes
        if key in self.storage_aliases:
            is_storage = True
        elif key in self.parser_aliases:
            is_storage = False
        else:
            is_storage = key in self.storage_properties
            
        if is_storage:
            if isinstance(value, list):
                self.storage_properties.setlist(key, value)
            else:
                self.storage_properties[key] = value
            self._content_modified = True
        else:
            if isinstance(value, list):
                self.parser_properties.setlist(key, value)
            else:
                self.parser_properties[key] = value
            self._parser_modified = True

    @staticmethod
    def create_item(access_point, properties):
        """Return a new item instance.
        
        Parameters:
            - ``access_point``: instance of the access point where the item
              will be reachable (after saving).
            - ``properties``: dictionnary or MultiDict of the item properties.
              These properties must be coherent with what is defined for the
              access point.
        
        Fixture
        >>> from _test.corks import CorkAccessPoint, cork_opener
        >>> ap = CorkAccessPoint()
        >>> properties = {}
        
        Test
        >>> item = Item.create_item(ap, properties)
        >>> assert item.format == ap.parser_name
        >>> assert isinstance(item, Item)
        
        """
        parser.load()
        
        storage_properties = dict((name, None) for name
                                  in access_point.get_storage_properties())
        
        item = Item.get_item_parser(access_point,
                                    storage_properties = storage_properties)
        
        # ItemProperties copies storage_properties in old_storage_properties
        # by default, but this is a nonsens in the case of a new item.
        item.old_storage_properties = MultiDict()
                
        # Needed because there is no binary data to parse properties from. We
        # set them manually.
        # XXX TODO: is this still true after item refactoring?
        item._loaded = True
        
        # Some parsers may need the ``_content`` property in their
        # ``serialize`` method.
        if '_content' not in properties:
            properties['_content'] = ''
        
        for name, value in properties.items():
            item[name] = value
        
        return item

    @staticmethod
    def get_item_parser(access_point, opener=StringIO, storage_properties={}):
        """Return an appropriate parser instance for the given format.
        
        Your kalamar distribution should have, at least, a parser for the
        ``binary`` format.
        
        >>> from _test.corks import CorkAccessPoint, cork_opener
        >>> ap = CorkAccessPoint()
        >>> ap.parser_name = 'binary'
        >>> Item.get_item_parser(ap, cork_opener, {'artist': 'muse'})
        ...  # doctest: +ELLIPSIS
        <kalamar.item.AtomItem object at 0x...>
        
        An invalid format will raise a ValueError:
        >>> ap.parser_name = 'I do not exist'
        >>> Item.get_item_parser(ap, cork_opener)
        Traceback (most recent call last):
        ...
        ParserNotAvailable: Unknown parser: I do not exist
        
        """
        parser.load()
        
        if access_point.parser_name is None:
            return Item(access_point, None, storage_properties)
        
        for subclass in utils.recursive_subclasses(Item):
            if getattr(subclass, 'format', None) == access_point.parser_name:
                return subclass(access_point, opener, storage_properties)
        
        raise utils.ParserNotAvailable('Unknown parser: ' +
                                       access_point.parser_name)

    @property
    def encoding(self):
        """Return the item encoding.

        Return the item encoding, based on what the parser can know from
        the item data or, if unable to do so, on what is specified in the
        access_point.

        """
        return self._access_point.default_encoding
    
    @property
    def content_modified(self):
        """Return if the item has been modified since creation.

        TODO: documentation

        """
        return self._content_modified
    
    @property
    def parser_modified(self):
        """Return if the item has been modified since creation.

        TODO: documentation

        """
        return self._parser_modified
    
    @property
    def filename(self):
        """Return the file path.

        If the item is stored in a file, return its path/name.
        Else return None

        """
        if hasattr(self._access_point, 'filename_for'):
            return self._access_point.filename_for(self)

    def keys(self):
        """Return properties keys."""
        return self.properties.keys()

    def serialize(self):
        """Return the item serialized into a string."""
        # Remove aliases
        properties = dict((name, self[name]) for name
                          in self.raw_properties.keys())
        return self._custom_serialize(properties)
    
    def _custom_serialize(self, properties):
        """Serialize item from its properties, return a data string.

        This method has to be overriden.

        This method must not worry about aliases, must not modify
        ``properties``, and must just return a string.

        """
        return ''

    def _parse_data(self):
        """Call ``_custom_parse_data`` and do some stuff to the result."""
        self._open()
        parse_data = self._custom_parse_data()
        for key, value in parse_data.items():
            self[key] = value

    def _custom_parse_data(self):
        """Parse properties from data, return a dictionnary.
        
        This method has to be extended.

        This method must not worry about aliases, must not modify
        ``properties``, and must just use super() and update and return the
        MultiDict.

        """
        return MultiDict()

    def _open(self):
        """Open the stream when called for the first time.
        
        >>> from _test.corks import CorkAccessPoint, cork_opener
        >>> ap = CorkAccessPoint()
        >>> item = Item(ap, cork_opener, {'toto': 'ToTo'})
        
        >>> item._stream
        >>> item._open()
        >>> stream = item._stream
        >>> print stream # doctest: +ELLIPSIS
        <open file '...kalamar/_test/toto', mode 'r' at ...>
        >>> item._open()
        >>> stream is item._stream
        True
        
        """
        if self._stream is None and self._opener is not None:
            self._stream = self._opener()



class AtomItem(Item):
    """An indivisible block of data.
    
    Give access to the binary data.
    
    """
    format = 'binary'
    
    def read(self):
        """Alias for item['_content']."""
        return self['_content']

    def write(self, value):
        """Alias for item['_content'] = value."""
        self['_content'] = value
    
    def _custom_parse_data(self):
        """Parse the whole item content."""
        properties = super(AtomItem, self)._custom_parse_data()
        properties['_content'] = self._stream.read()
        return properties
        
    def _custom_serialize(self, properties):
        """Return the item content."""
        return properties['_content']



class CapsuleItem(Item):
    """An ordered list of Items (atoms or capsules).

    This is an abstract class.

    """
    @property
    def subitems(self):
        if not hasattr(self, '_subitems'):
            self._subitems = utils.ModificationTrackingList(
                self._load_subitems())
        return self._subitems
        
    def _load_subitems(self):
        raise NotImplementedError('Abstract class')



class AliasedMultiDict(object):
    """Helper class

    TODO: documentation and tests

    """
    def __init__(self, data, aliases):
        self.data = data
        self.aliases = aliases

    def __contains__(self, key):
        return key in self.keys()

    def __getitem__(self, key):
        return self.data[self.aliases.get(key, key)]

    def __setitem__(self, key, value):
        self.data[self.aliases.get(key, key)] = value

    def keys(self):
        return self.aliases.keys() + self.data.keys()

    def getlist(self, key, type=None):
        return self.data.getlist(self.aliases.get(key, key), type)
