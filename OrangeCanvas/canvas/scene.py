"""
Canvas Graphics Scene

"""

import logging
from operator import attrgetter

from xml.sax.saxutils import escape

from PyQt4.QtGui import QGraphicsScene, QPainter, QBrush, \
                        QGraphicsItem

from PyQt4.QtCore import Qt, QPointF, QRectF, QSizeF, QLineF, QBuffer

from PyQt4.QtCore import pyqtSignal as Signal
from PyQt4.QtCore import PYQT_VERSION_STR


from .. import scheme

from . import items
from .layout import AnchorLayout
from .items.utils import toGraphicsObjectIfPossible, typed_signal_mapper

log = logging.getLogger(__name__)


NodeItemSignalMapper = typed_signal_mapper(items.NodeItem)


class CanvasScene(QGraphicsScene):
    """A Graphics Scene for displaying and editing an Orange Scheme.
    """

    node_item_added = Signal(items.NodeItem)
    """An node item has been added to the scene"""

    node_item_removed = Signal(items.LinkItem)
    """An node item has been removed from the scene"""

    node_item_position_changed = Signal(items.NodeItem, QPointF)
    """The position of a node has changed"""

    node_item_double_clicked = Signal(items.NodeItem)
    """An node item has been double clicked"""

    node_item_activated = Signal(items.NodeItem)
    """An node item has been activated (clicked)"""

    node_item_hovered = Signal(items.NodeItem)
    """An node item has been hovered"""

    link_item_added = Signal(items.LinkItem)
    """A new link item has been added to the scene"""

    link_item_removed = Signal(items.LinkItem)
    """Link item has been removed"""

    link_item_hovered = Signal(items.LinkItem)
    """Link item has been hovered"""

    annotation_added = Signal(items.annotationitem.Annotation)
    """Annotation item has been added"""

    annotation_removed = Signal(items.annotationitem.Annotation)
    """Annotation item has been removed"""

    def __init__(self, *args, **kwargs):
        QGraphicsScene.__init__(self, *args, **kwargs)

        self.scheme = None
        self.registry = None

        # All node items
        self.__node_items = []
        # Mapping from SchemeNodes to canvas items
        self.__item_for_node = {}
        # All link items
        self.__link_items = []
        # Mapping from SchemeLinks to canvas items.
        self.__item_for_link = {}

        # All annotation items
        self.__annotation_items = []
        # Mapping from SchemeAnnotations to canvas items.
        self.__item_for_annotation = {}

        # Is the scene editable
        self.editable = True

        # Anchor Layout
        self.__anchor_layout = AnchorLayout()
        self.addItem(self.__anchor_layout)

        self.__channel_names_visible = True

        self.user_interaction_handler = None

        self.activated_mapper = NodeItemSignalMapper(self)
        self.activated_mapper.pyMapped.connect(
            self.node_item_activated
        )

        self.hovered_mapper = NodeItemSignalMapper(self)
        self.hovered_mapper.pyMapped.connect(
            self.node_item_hovered
        )

        self.position_change_mapper = NodeItemSignalMapper(self)
        self.position_change_mapper.pyMapped.connect(
            self._on_position_change
        )

        log.info("'%s' intitialized." % self)

    def clear_scene(self):
        self.scheme = None
        self.__node_items = []
        self.__item_for_node = {}
        self.__link_items = []
        self.__item_for_link = {}
        self.__annotation_items = []
        self.__item_for_annotation = {}

        self.__anchor_layout.deleteLater()

        self.user_interaction_handler = None

        self.clear()
        log.info("'%s' cleared." % self)

    def set_scheme(self, scheme):
        """Set the scheme to display and edit. Populates the scene
        with nodes and links already in the scheme.

        """
        if self.scheme is not None:
            # Clear the old scheme
            self.scheme.node_added.disconnect(self.add_node)
            self.scheme.node_removed.disconnect(self.remove_node)

            self.scheme.link_added.disconnect(self.add_link)
            self.scheme.link_removed.disconnect(self.remove_link)

            self.scheme.annotation_added.disconnect(self.add_annotation)
            self.scheme.annotation_removed.disconnect(self.remove_annotation)

            self.scheme.node_state_changed.disconnect(
                self.on_widget_state_change
            )
            self.scheme.channel_state_changed.disconnect(
                self.on_link_state_change
            )

            self.clear_scene()

        log.info("Setting scheme '%s' on '%s'" % (scheme, self))

        self.scheme = scheme
        if self.scheme is not None:
            self.scheme.node_added.connect(self.add_node)
            self.scheme.node_removed.connect(self.remove_node)

            self.scheme.link_added.connect(self.add_link)
            self.scheme.link_removed.connect(self.remove_link)

            self.scheme.annotation_added.connect(self.add_annotation)
            self.scheme.annotation_removed.connect(self.remove_annotation)

            self.scheme.node_state_changed.connect(
                self.on_widget_state_change
            )
            self.scheme.channel_state_changed.connect(
                self.on_link_state_change
            )

            self.scheme.topology_changed.connect(self.on_scheme_change)

        for node in scheme.nodes:
            self.add_node(node)

        for link in scheme.links:
            self.add_link(link)

        for annot in scheme.annotations:
            self.add_annotation(annot)

    def set_registry(self, registry):
        """Set the widget registry.
        """
        log.info("Setting registry '%s on '%s'." % (registry, self))
        self.registry = registry

    def set_anchor_layout(self, layout):
        if self.__anchor_layout != layout:
            if self.__anchor_layout:
                self.__anchor_layout.deleteLater()
                self.__anchor_layout = None

            self.__anchor_layout = layout

    def anchor_layout(self):
        return self.__anchor_layout

    def set_channel_names_visible(self, visible):
        self.__channel_names_visible = visible
        for link in self.__link_items:
            link.setChannelNamesVisible(visible)

    def channel_names_visible(self):
        return self.__channel_names_visible

    def add_node_item(self, item):
        """Add a :class:`NodeItem` instance to the scene.
        """
        if item in self.__node_items:
            raise ValueError("%r is already in the scene." % item)

        if item.pos().isNull():
            if self.__node_items:
                pos = self.__node_items[-1].pos() + QPointF(150, 0)
            else:
                pos = QPointF(150, 150)

            item.setPos(pos)

        # Set signal mappings
        self.activated_mapper.setPyMapping(item, item)
        item.activated.connect(self.activated_mapper.pyMap)

        self.hovered_mapper.setPyMapping(item, item)
        item.hovered.connect(self.hovered_mapper.pyMap)

        self.position_change_mapper.setPyMapping(item, item)
        item.positionChanged.connect(self.position_change_mapper.pyMap)

        self.addItem(item)

        self.__node_items.append(item)

        self.node_item_added.emit(item)

        log.info("Added item '%s' to '%s'" % (item, self))
        return item

    def add_node(self, node):
        """Add and return a default constructed `NodeItem` for a
        `SchemeNode` instance. If the node is already in the scene
        do nothing and just return its item.

        """
        if node in self.__item_for_node:
            # Already added
            return self.__item_for_node[node]

        item = self.new_node_item(node.description)

        if node.position:
            pos = QPointF(*node.position)
            item.setPos(pos)

        self.__item_for_node[node] = item

        node.position_changed.connect(self.__on_node_pos_changed)
        node.title_changed.connect(item.setTitle)
        node.progress_changed.connect(item.setProgress)
        node.processing_state_changed.connect(item.setProcessingState)
        return self.add_node_item(item)

    def new_node_item(self, widget_desc, category_desc=None):
        """Construct an new `NodeItem` from a `WidgetDescription`.
        Optionally also set `CategoryDescription`.

        """
        item = items.NodeItem()
        item.setWidgetDescription(widget_desc)

        if category_desc is None and self.registry and widget_desc.category:
            category_desc = self.registry.category(widget_desc.category)

        if category_desc is None and self.registry is not None:
            try:
                category_desc = self.registry.category(widget_desc.category)
            except KeyError:
                pass

        if category_desc is not None:
            item.setWidgetCategory(category_desc)

        return item

    def remove_node_item(self, item):
        """Remove `item` (:class:`NodeItem`) from the scene.
        """
        self.activated_mapper.removePyMappings(item)
        self.hovered_mapper.removePyMappings(item)

        item.hide()
        self.removeItem(item)
        self.__node_items.remove(item)

        self.node_item_removed.emit(item)

        log.info("Removed item '%s' from '%s'" % (item, self))

    def remove_node(self, node):
        """Remove the `NodeItem` instance that was previously constructed for
        a `SchemeNode` node using the `add_node` method.

        """
        item = self.__item_for_node.pop(node)

        node.position_changed.disconnect(self.__on_node_pos_changed)
        node.title_changed.disconnect(item.setTitle)
        node.progress_changed.disconnect(item.setProgress)
        node.processing_state_changed.disconnect(item.setProcessingState)

        self.remove_node_item(item)

    def node_items(self):
        """Return all :class:`NodeItem` instances in the scene.
        """
        return list(self.__node_items)

    def add_link_item(self, item):
        """Add a link (:class:`LinkItem`)to the scene.
        """
        if item.scene() is not self:
            self.addItem(item)

        self.__link_items.append(item)

        self.link_item_added.emit(item)

        log.info("Added link %r -> %r to '%s'" % \
                 (item.sourceItem.title, item.sinkItem.title, self))

        self.__anchor_layout.invalidateLink(item)

        return item

    def add_link(self, scheme_link):
        """Create and add a `LinkItem` instance for a `SchemeLink`
        instance. If the link is already in the scene do nothing
        and just return its `LinkItem`.

        """
        if scheme_link in self.__item_for_link:
            return self.__item_for_link[scheme_link]

        source = self.__item_for_node[scheme_link.source_node]
        sink = self.__item_for_node[scheme_link.sink_node]

        item = self.new_link_item(source, scheme_link.source_channel,
                                  sink, scheme_link.sink_channel)

        item.setEnabled(scheme_link.enabled)

        scheme_link.enabled_changed.connect(item.setEnabled)

        self.add_link_item(item)
        self.__item_for_link[scheme_link] = item
        return item

    def new_link_item(self, source_item, source_channel,
                      sink_item, sink_channel):
        """Construct and return a new `LinkItem`
        """
        item = items.LinkItem()
        item.setSourceItem(source_item)
        item.setSinkItem(sink_item)
        fmt = "<b>{0}</b>&nbsp;-->&nbsp;<b>{1}</b>"
        item.setToolTip(
            fmt.format(escape(source_channel.name),
                       escape(sink_channel.name))
        )

        item.setSourceName(source_channel.name)
        item.setSinkName(sink_channel.name)
        item.setChannelNamesVisible(self.__channel_names_visible)

        return item

    def remove_link_item(self, item):
        """Remove a link (:class:`LinkItem`) from the scene.
        """
        self.__link_items.remove(item)

        # Remove the anchor points.
        item.removeLink()
        self.removeItem(item)
        self.link_item_removed.emit(item)

        log.info("Removed link '%s' from '%s'" % (item, self))

        return item

    def remove_link(self, scheme_link):
        """ Remove a `LinkItem` instance that was previously constructed for
        a `SchemeLink` node using the `add_link` method.

        """
        item = self.__item_for_link.pop(scheme_link)
        scheme_link.enabled_changed.disconnect(item.setEnabled)
        self.remove_link_item(item)

    def link_items(self):
        """Return all :class:`LinkItems` in the scene.

        """
        return list(self.__link_items)

    def add_annotation_item(self, annotation):
        """Add an `Annotation` item to the scene.

        """
        self.__annotation_items.append(annotation)
        self.addItem(annotation)
        self.annotation_added.emit(annotation)
        return annotation

    def add_annotation(self, scheme_annot):
        """Create a new item for :class:`SchemeAnnotation` and add it
        to the scene. If the `scheme_annot` is already in the scene do
        nothing and just return its item.

        """
        if scheme_annot in self.__item_for_annotation:
            # Already added
            return self.__item_for_annotation[scheme_annot]

        if isinstance(scheme_annot, scheme.SchemeTextAnnotation):
            item = items.TextAnnotation()
            item.setPlainText(scheme_annot.text)
            x, y, w, h = scheme_annot.rect
            item.setPos(x, y)
            item.resize(w, h)
            item.setTextInteractionFlags(Qt.TextEditorInteraction)
            scheme_annot.text_changed.connect(item.setPlainText)

        elif isinstance(scheme_annot, scheme.SchemeArrowAnnotation):
            item = items.ArrowAnnotation()
            start, end = scheme_annot.start_pos, scheme_annot.end_pos
            item.setLine(QLineF(QPointF(*start), QPointF(*end)))

        scheme_annot.geometry_changed.connect(
            self.__on_scheme_annot_geometry_change
        )

        self.add_annotation_item(item)
        self.__item_for_annotation[scheme_annot] = item

        return item

    def remove_annotation_item(self, annotation):
        """Remove an `Annotation` item from the scene.

        """
        self.__annotation_items.remove(annotation)
        self.removeItem(annotation)
        self.annotation_removed.emit(annotation)

    def remove_annotation(self, scheme_annotation):
        item = self.__item_for_annotation.pop(scheme_annotation)

        scheme_annotation.geometry_changed.disconnect(
            self.__on_scheme_annot_geometry_change
        )

        if isinstance(scheme_annotation, scheme.SchemeTextAnnotation):
            scheme_annotation.text_changed.disconnect(
                item.setPlainText
            )

        self.remove_annotation_item(item)

    def annotation_items(self):
        """Return all `Annotation` items in the scene.

        """
        return self.__annotation_items

    def item_for_annotation(self, scheme_annotation):
        return self.__item_for_annotation[scheme_annotation]

    def annotation_for_item(self, item):
        rev = dict(reversed(item) \
                   for item in self.__item_for_annotation.items())
        return rev[item]

    def commit_scheme_node(self, node):
        """Commit the `node` into the scheme.
        """
        if not self.editable:
            raise Exception("Scheme not editable.")

        if node not in self.__item_for_node:
            raise ValueError("No 'NodeItem' for node.")

        item = self.__item_for_node[node]

        try:
            self.scheme.add_node(node)
        except Exception:
            log.error("An unexpected error occurred while commiting node '%s'",
                      node, exc_info=True)
            # Cleanup (remove the node item)
            self.remove_node_item(item)
            raise

        log.info("Commited node '%s' from '%s' to '%s'" % \
                 (node, self, self.scheme))

    def commit_scheme_link(self, link):
        """Commit a scheme link.
        """
        if not self.editable:
            raise Exception("Scheme not editable")

        if link not in self.__item_for_link:
            raise ValueError("No 'LinkItem' for link.")

        self.scheme.add_link(link)
        log.info("Commited link '%s' from '%s' to '%s'" % \
                 (link, self, self.scheme))

    def node_for_item(self, item):
        """Return the `SchemeNode` for the `item`.
        """
        rev = dict([(v, k) for k, v in self.__item_for_node.items()])
        return rev[item]

    def item_for_node(self, node):
        """Return the :class:`NodeItem` instance for a :class:`SchemeNode`.
        """
        return self.__item_for_node[node]

    def link_for_item(self, item):
        """Return the `SchemeLink for `item` (:class:`LinkItem`).
        """
        rev = dict([(v, k) for k, v in self.__item_for_link.items()])
        return rev[item]

    def item_for_link(self, link):
        """Return the :class:`LinkItem` for a :class:`SchemeLink`
        """
        return self.__item_for_link[link]

    def selected_node_items(self):
        """Return the selected :class:`NodeItem`'s.
        """
        return [item for item in self.__node_items if item.isSelected()]

    def selected_annotation_items(self):
        """Return the selected :class:`Annotation`'s
        """
        return [item for item in self.__annotation_items if item.isSelected()]

    def node_links(self, node_item):
        """Return all links from the `node_item` (:class:`NodeItem`).
        """
        return self.node_output_links(node_item) + \
               self.node_input_links(node_item)

    def node_output_links(self, node_item):
        """Return a list of all output links from `node_item`.
        """
        return [link for link in self.__link_items
                if link.sourceItem == node_item]

    def node_input_links(self, node_item):
        """Return a list of all input links for `node_item`.
        """
        return [link for link in self.__link_items
                if link.sinkItem == node_item]

    def neighbor_nodes(self, node_item):
        """Return a list of `node_item`'s (class:`NodeItem`) neighbor nodes.
        """
        neighbors = map(attrgetter("sourceItem"),
                        self.node_input_links(node_item))

        neighbors.extend(map(attrgetter("sinkItem"),
                             self.node_output_links(node_item)))
        return neighbors

    def on_widget_state_change(self, widget, state):
        pass

    def on_link_state_change(self, link, state):
        pass

    def on_scheme_change(self, ):
        pass

    def _on_position_change(self, item):
        # Invalidate the anchor point layout and schedule a layout.
        self.__anchor_layout.invalidateNode(item)

        self.node_item_position_changed.emit(item, item.pos())

    def __on_node_pos_changed(self, pos):
        node = self.sender()
        item = self.__item_for_node[node]
        item.setPos(*pos)

    def __on_scheme_annot_geometry_change(self):
        annot = self.sender()
        item = self.__item_for_annotation[annot]
        if isinstance(annot, scheme.SchemeTextAnnotation):
            item.setGeometry(QRectF(*annot.rect))
        elif isinstance(annot, scheme.SchemeArrowAnnotation):
            p1 = item.mapFromScene(QPointF(*annot.start_pos))
            p2 = item.mapFromScene(QPointF(*annot.end_pos))
            item.setLine(QLineF(p1, p2))
        else:
            pass

    def item_at(self, pos, type_or_tuple=None):
        rect = QRectF(pos - QPointF(1.5, 1.5), QSizeF(3, 3))
        items = self.items(rect)
        if type_or_tuple:
            items = [i for i in items if isinstance(i, type_or_tuple)]

        return items[0] if items else None

    if PYQT_VERSION_STR < "4.9":
        # For QGraphicsObject subclasses items, itemAt ... return a
        # QGraphicsItem wrapper instance and not the actual class instance.
        def itemAt(self, *args, **kwargs):
            item = QGraphicsScene.itemAt(self, *args, **kwargs)
            return toGraphicsObjectIfPossible(item)

        def items(self, *args, **kwargs):
            items = QGraphicsScene.items(self, *args, **kwargs)
            return map(toGraphicsObjectIfPossible, items)

        def selectedItems(self, *args, **kwargs):
            return map(toGraphicsObjectIfPossible,
                       QGraphicsScene.selectedItems(self, *args, **kwargs))

        def collidingItems(self, *args, **kwargs):
            return map(toGraphicsObjectIfPossible,
                       QGraphicsScene.collidingItems(self, *args, **kwargs))

        def focusItem(self, *args, **kwargs):
            item = QGraphicsScene.focusItem(self, *args, **kwargs)
            return toGraphicsObjectIfPossible(item)

        def mouseGrabberItem(self, *args, **kwargs):
            item = QGraphicsScene.mouseGrabberItem(self, *args, **kwargs)
            return toGraphicsObjectIfPossible(item)

    def mousePressEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.mousePressEvent(event):
            return

        # Right (context) click on the node item. If the widget is not
        # in the current selection then select the widget (only the widget).
        # Else simply return and let customContextMenuReqested signal
        # handle it
        shape_item = self.item_at(event.scenePos(), items.NodeItem)
        if shape_item and event.button() == Qt.RightButton and \
                shape_item.flags() & QGraphicsItem.ItemIsSelectable:
            if not shape_item.isSelected():
                self.clearSelection()
                shape_item.setSelected(True)

        return QGraphicsScene.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.mouseMoveEvent(event):
            return

        return QGraphicsScene.mouseMoveEvent(self, event)

    def mouseReleaseEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.mouseReleaseEvent(event):
            return
        return QGraphicsScene.mouseReleaseEvent(self, event)

    def mouseDoubleClickEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.mouseDoubleClickEvent(event):
            return

        return QGraphicsScene.mouseDoubleClickEvent(self, event)

    def keyPressEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.keyPressEvent(event):
            return
        return QGraphicsScene.keyPressEvent(self, event)

    def keyReleaseEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.keyReleaseEvent(event):
            return
        return QGraphicsScene.keyReleaseEvent(self, event)

    def set_user_interaction_handler(self, handler):
        if self.user_interaction_handler and \
                not self.user_interaction_handler.finished:
            self.user_interaction_handler.cancel()

        log.info("Setting interaction '%s' to '%s'" % (handler, self))

        self.user_interaction_handler = handler
        if handler:
            handler.start()

    def __str__(self):
        return "%s(objectName=%r, ...)" % \
                (type(self).__name__, str(self.objectName()))


def grab_svg(scene):
    """Return a SVG rendering of the scene contents.
    """
    from PyQt4.QtSvg import QSvgGenerator
    svg_buffer = QBuffer()
    gen = QSvgGenerator()
    gen.setOutputDevice(svg_buffer)

    items_rect = scene.itemsBoundingRect().adjusted(-10, -10, 10, 10)

    if items_rect.isNull():
        items_rect = QRectF(0, 0, 10, 10)

    width, height = items_rect.width(), items_rect.height()
    rect_ratio = float(width) / height

    # Keep a fixed aspect ratio.
    aspect_ratio = 1.618
    if rect_ratio > aspect_ratio:
        height = int(height * rect_ratio / aspect_ratio)
    else:
        width = int(width * aspect_ratio / rect_ratio)

    target_rect = QRectF(0, 0, width, height)
    source_rect = QRectF(0, 0, width, height)
    source_rect.moveCenter(items_rect.center())

    gen.setSize(target_rect.size().toSize())
    gen.setViewBox(target_rect)

    painter = QPainter(gen)

    # Draw background.
    painter.setBrush(QBrush(Qt.white))
    painter.drawRect(target_rect)

    # Render the scene
    scene.render(painter, target_rect, source_rect)
    painter.end()

    return unicode(svg_buffer.buffer())
