"""Reusable main application shell with sidebar and content area."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from ui.widgets.decorative_panel import DecorativePanel
from ui.widgets.sidebar_nav import SidebarNav


class AppShell(QFrame):
    """Shared shell that composes sidebar navigation and a content host."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("appShell")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar_nav = SidebarNav()
        main_layout.addWidget(self.sidebar_nav)

        self.content_surface = QFrame()
        self.content_surface.setObjectName("appShellContentSurface")
        content_layout = QVBoxLayout(self.content_surface)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(20)
        self._content_layout = content_layout

        self.content_host = QFrame()
        self.content_host.setObjectName("appShellContentHost")
        self.content_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        host_layout = QVBoxLayout(self.content_host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(18)
        self._host_layout = host_layout

        content_layout.addWidget(self.content_host, 1)
        main_layout.addWidget(self.content_surface, 1)

        self._apply_styles()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#appShell {
                background-color: #0f0f1e;
            }
            QFrame#appShellContentSurface {
                background-color: transparent;
            }
            QFrame#appShellContentHost {
                background-color: transparent;
            }
            """
        )

    def add_content_widget(self, widget: QWidget, stretch: int = 0, alignment: Qt.AlignmentFlag = Qt.Alignment()) -> None:
        """Append a widget to the shell's content host."""
        self._host_layout.addWidget(widget, stretch, alignment)

    def clear_content(self) -> None:
        """Remove all content widgets from the host layout."""
        while self._host_layout.count():
            item = self._host_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    def content_layout(self) -> QVBoxLayout:
        return self._host_layout


__all__ = ["AppShell"]
