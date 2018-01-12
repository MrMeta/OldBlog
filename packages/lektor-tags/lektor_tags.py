# -*- coding: utf-8 -*-
import pkg_resources
import posixpath

from lektor.build_programs import BuildProgram
from lektor.environment import Expression, FormatExpression
from lektor.pluginsystem import Plugin
from lektor.sourceobj import VirtualSourceObject
from lektor.utils import build_url, bool_from_string

DEFAULT_ITEMS_QUERY = 'this.parent.children.filter(F.tags.contains(tag))'
DEFAULT_URL_PATH_EXP = '{{ dest_path }}tag/{{ tag }}'


def _ensure_slash(s):
    return s if s.endswith('/') else s + '/'


class TagPage(VirtualSourceObject):
    def __init__(self, parent, tag):
        VirtualSourceObject.__init__(self, parent)
        self.plugin = parent.pad.env.plugins['tags']
        self.tag = tag
        self.i_want_to_live = self.pad

    @property
    def items(self):
        """Pages that have tag"""
        items_exp = Expression(self.pad.env, self.plugin.get_items_expression())
        return items_exp.evaluate(self.pad, this=self, values={'tag': self.tag})

    @property
    def num_of_items(self):
        return len(self.items.all())

    @property
    def path(self):
        return build_url([self.plugin.get_dest_path(), '@tag', self.tag])

    @property
    def url_path(self):
        try:
            return TagsPlugin.reverse_url_map[self.path]
        except KeyError:
            if self.plugin.ignore_missing():
                return ''
            raise

    @property
    def template_name(self):
        return self.plugin.get_template_filename()

    def set_url_path(self, url_path):
        url_path = _ensure_slash(url_path)
        TagsPlugin.url_map[url_path] = self
        TagsPlugin.reverse_url_map[self.path] = url_path


class TagPageBuildProgram(BuildProgram):
    def produce_artifacts(self):
        self.declare_artifact(
            posixpath.join(self.source.url_path, 'index.html'),
            sources=list(self.source.iter_source_filenames()))

    def build_artifact(self, artifact):
        artifact.render_template_into(self.source.template_name,
                                      this=self.source)


# TODO: find better name than TagRootPage
class TagRootPage(VirtualSourceObject):
    def __init__(self, parent):
        """construct TagRootPage

        Args:
            parent:     Source object that is parent of TagRootPage
        """
        VirtualSourceObject.__init__(self, parent)
        self.plugin = parent.pad.env.plugins['tags']
        self.i_want_to_live = self.pad

    @property
    def tags(self):
        tag_list = []
        for url_path, tag in self.plugin.url_map.items():
            tag_list.append((tag.tag, url_path, len(tag.items.all())))

        return sorted(tag_list, key=lambda x: x[2], reverse=True)

    @property
    def path(self):
        return build_url([self.plugin.get_dest_path(), '@tag'])

    @property
    def url_path(self):
        return build_url([self.plugin.get_dest_path(), 'tag'])

    @property
    def template_name(self):
        return self.plugin.get_root_template_filename()


class TagRootPageBuildProgram(BuildProgram):
    def produce_artifacts(self):
        self.declare_artifact(
            posixpath.join(self.source.url_path, 'index.html'),
            sources=list(self.source.iter_source_filenames()))

    def build_artifact(self, artifact):
        artifact.render_template_into(self.source.template_name,
                                      this=self.source)


class TagsPlugin(Plugin):
    name = u'blog-posts'
    description = u'Lektor customization just for emptysqua.re.'
    generated = False
    url_map = {}            # key: url_path, value: TagPage
    reverse_url_map = {}    # key: TagPage's path, value: url_path
    root_page = None

    def on_setup_env(self, **extra):
        pkg_dir = pkg_resources.resource_filename('lektor_tags', 'templates')
        self.env.jinja_env.loader.searchpath.append(pkg_dir)
        self.env.add_build_program(TagPage, TagPageBuildProgram)
        self.env.add_build_program(TagRootPage, TagPageBuildProgram)

        @self.env.urlresolver
        def tag_resolver(parent, url_path):
            """Resolves TagPage that matches url_path.

            This function is usually called when a client requests the url. (uncertain)

            Args:
                parent:     Source object that has the virtual object as child.
                url_path
            """
            if not self.has_config():
                return

            u = build_url([parent.url_path] + url_path, trailing_slash=True)
            return TagsPlugin.url_map.get(u)

        @self.env.urlresolver
        def tag_root_resolver(parent, url_path):
            if not self.has_config():
                return

            u = build_url([parent.url_path] + url_path, trailing_slash=True)
            if u == TagsPlugin.root_page.url_path:
                return TagsPlugin.root_page
            return None

        @self.env.virtualpathresolver('tag')
        def tag_and_root_virtual_path_resolver(parent, pieces):
            """Resolves Virtual source object(TagPage or TagRootPage) that matches the virtual path.

            This function is usually called when a path that includes the virtual marker(@)
            is converted to url by template's 'url' filter.

            Args:
                parent:     Source object that has the virtual object as child.
                pieces:     Rest after '@tag/' (List)

            Example:
                if virtual path is '/blog/@tag/test', then 'parent' is '/blog', 'pieces' is ['test'].
                if virtual path is '/@tag/', then 'parent' is '/', 'pieces' is [].
            """
            if not self.has_config():
                return

            if parent.path == self.get_dest_path() and len(pieces) == 1:
                return TagPage(parent, pieces[0])
            elif parent.path == self.get_dest_path() and len(pieces) == 0:
                return TagsPlugin.root_page

        @self.env.generator
        def generate_tag_pages(source):
            """Creates TagPage relative to another page that matches the 'parent' option
            and has tags field.

            This function is usually called while build.

            Args:
                source:     All source object
            """
            if not self.has_config():
                return

            parent_path = self.get_parent_path()
            if source.path != parent_path:
                return

            pad = source.pad
            url_exp = FormatExpression(self.env, self.get_url_path_expression())

            for tag in self.get_all_tags(source):
                page = TagPage(source, tag)
                url_path = url_exp.evaluate(pad, values={'dest_path': self.get_dest_path(), 'tag': tag})
                page.set_url_path(url_path)
                yield page

        @self.env.generator
        def generate_tag_root_page(source):
            if not self.has_config():
                return

            dest_path = self.get_dest_path()
            if source.path != dest_path:
                return

            dest = source.pad.get(self.get_dest_path())
            page = TagRootPage(dest)
            TagsPlugin.root_page = page
            yield page

    def get_all_tags(self, parent):
        exp = Expression(self.env, self.get_tags_expression())
        tags = exp.evaluate(parent.pad, values={'parent': parent})
        return sorted(set(tags))

    def has_config(self):
        return not self.get_config().is_new

    def get_items_expression(self):
        return self.get_config().get('items', DEFAULT_ITEMS_QUERY)

    def get_tags_expression(self):
        tags_exp = self.get_config().get('tags')
        if tags_exp:
            return tags_exp

        return 'parent.children.distinct("%s")' % self.get_tag_field_name()

    def get_url_path_expression(self):
        return self.get_config().get('url_path', DEFAULT_URL_PATH_EXP)

    def get_parent_path(self):
        p = self.get_config().get('parent')
        if not p:
            raise RuntimeError('Set the "parent" option in %s'
                               % self.config_filename)

        return p

    def get_dest_path(self):
        return _ensure_slash(self.get_config().get('dest', self.get_parent_path()))

    def get_template_filename(self):
        filename = self.get_config().get('template')
        if filename:
            return filename

        return 'lektor_tags_default_template.html'

    def get_root_template_filename(self):
        filename = self.get_config().get('root_template')
        if filename:
            return filename

        return 'lektor_tags_root_default_template.html'

    def get_tag_field_name(self):
        return self.get_config().get('tags_field', 'tags')

    def ignore_missing(self):
        return bool_from_string(self.get_config().get('ignore_missing'), False)
