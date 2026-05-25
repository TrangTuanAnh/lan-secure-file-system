"""Right-side drawer for room members and add-member flow."""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QComboBox, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from ui.fonts import app_font, ui_font, ui_font_family
from ui.widgets.error_label import ErrorLabel
from ui.widgets.member_context_menu import MemberContextMenu
from ui.widgets.modern_button import PALETTE, ModernButton
from ui.widgets.modern_lineedit import ModernLineEdit
from ui.widgets.status_badge import StatusBadge


class RoomMembersDrawer(QFrame):
    """Slide-out drawer with member list and add-member form."""

    add_member_requested = Signal(str, str)
    set_role_requested = Signal(dict)
    remove_member_requested = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._drawer_width = 404
        self._is_open = False
        self._animating = False
        self._animation = QPropertyAnimation(self, b"geometry", self)
        self._animation.finished.connect(self._on_animation_finished)

        self.setObjectName("roomMembersDrawer")
        self.setFocusPolicy(Qt.StrongFocus)
        self.hide()

        self.error_toast = ErrorLabel(parent=self)
        self._context_menu: Optional[MemberContextMenu] = None
        self._current_member_for_context: Optional[dict[str, Any]] = None

        self._build_ui()
        self._apply_styles()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(16)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)

        self.back_button = ModernButton("Back")
        self.back_button.setMinimumWidth(84)
        self.back_button.set_button_style(
            background_color=PALETTE.surface,
            background_alt=PALETTE.surface_alt,
        )
        self.back_button.clicked.connect(self.show_members_view)
        self.back_button.hide()
        header.addWidget(self.back_button)

        self.title_label = QLabel("Room Members")
        self.title_label.setObjectName("drawerTitle")
        self.title_label.setFont(app_font(16, 700))
        header.addWidget(self.title_label, 1)

        self.close_button = ModernButton("Close")
        self.close_button.setMinimumWidth(92)
        self.close_button.set_button_style(
            background_color=PALETTE.surface,
            background_alt=PALETTE.surface_alt,
        )
        self.close_button.clicked.connect(self.close_drawer)
        header.addWidget(self.close_button)
        root.addLayout(header)

        self.stack = QStackedWidget()
        self.stack.setObjectName("membersDrawerStack")
        root.addWidget(self.stack, 1)

        self.members_page = QWidget()
        self.members_page.setObjectName("membersDrawerMembersPage")
        members_layout = QVBoxLayout(self.members_page)
        members_layout.setContentsMargins(0, 0, 0, 0)
        members_layout.setSpacing(14)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)
        self.summary_label = QLabel("Loading members...")
        self.summary_label.setObjectName("drawerSubtitle")
        self.summary_label.setFont(ui_font(9))
        top_row.addWidget(self.summary_label, 1)
        self.add_member_button = ModernButton("Add Member")
        self.add_member_button.clicked.connect(self.show_add_member_view)
        top_row.addWidget(self.add_member_button)
        members_layout.addLayout(top_row)

        self.members_scroll = QScrollArea()
        self.members_scroll.setObjectName("membersDrawerScroll")
        self.members_scroll.setWidgetResizable(True)
        self.members_scroll.setFrameShape(QFrame.NoFrame)
        members_layout.addWidget(self.members_scroll, 1)

        self.members_content = QWidget()
        self.members_content.setObjectName("membersDrawerMembersContent")
        self.members_rows = QVBoxLayout(self.members_content)
        self.members_rows.setContentsMargins(0, 0, 0, 0)
        self.members_rows.setSpacing(10)
        self.members_scroll.setWidget(self.members_content)
        self.stack.addWidget(self.members_page)

        self.add_member_page = QWidget()
        self.add_member_page.setObjectName("membersDrawerAddPage")
        add_layout = QVBoxLayout(self.add_member_page)
        add_layout.setContentsMargins(0, 0, 0, 0)
        add_layout.setSpacing(14)

        add_subtitle = QLabel("Enter the user's UUID. The user can copy it from Account profile.")
        add_subtitle.setObjectName("drawerSubtitle")
        add_subtitle.setWordWrap(True)
        add_subtitle.setFont(ui_font(9))
        add_layout.addWidget(add_subtitle)

        add_layout.addWidget(self._field_label("User ID"))
        self.user_id_input = ModernLineEdit("Enter user UUID")
        add_layout.addWidget(self.user_id_input)

        add_layout.addWidget(self._field_label("Role"))
        self.role_combo = QComboBox()
        self.role_combo.setObjectName("membersRoleCombo")
        self.role_combo.addItems(["OWNER", "MEMBER", "VIEWER"])
        self.role_combo.setCurrentText("MEMBER")
        self.role_combo.setEditable(False)
        add_layout.addWidget(self.role_combo)
        add_layout.addStretch()

        add_actions = QHBoxLayout()
        add_actions.setContentsMargins(0, 0, 0, 0)
        add_actions.setSpacing(12)
        self.cancel_add_button = ModernButton("Cancel")
        self.cancel_add_button.set_button_style(
            background_color=PALETTE.surface,
            background_alt=PALETTE.surface_alt,
        )
        self.cancel_add_button.clicked.connect(self.show_members_view)
        add_actions.addWidget(self.cancel_add_button)

        self.submit_add_button = ModernButton("Add Member")
        self.submit_add_button.clicked.connect(self._submit_add_member)
        add_actions.addWidget(self.submit_add_button)
        add_layout.addLayout(add_actions)
        self.stack.addWidget(self.add_member_page)

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        label.setFont(app_font(10, 600))
        return label

    def _apply_styles(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(-2, 0)
        shadow.setColor(QColor(0, 200, 83, 34))
        self.setGraphicsEffect(shadow)

        self.setStyleSheet(
            f"""
            QFrame#roomMembersDrawer {{
                background-color: rgba(15, 15, 30, 248);
                border: 1px solid rgba(0, 200, 83, 38);
                border-top-left-radius: 26px;
                border-bottom-left-radius: 26px;
            }}
            QStackedWidget#membersDrawerStack,
            QWidget#membersDrawerMembersPage,
            QWidget#membersDrawerAddPage,
            QWidget#membersDrawerMembersContent,
            QScrollArea#membersDrawerScroll {{
                background: transparent;
                border: none;
            }}
            QFrame#memberRow {{
                background-color: rgba(26, 26, 46, 220);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 18px;
            }}
            QFrame#memberRow:hover {{
                background-color: rgba(28, 28, 48, 240);
                border: 1px solid rgba(0, 200, 83, 0.25);
            }}
            QComboBox#membersRoleCombo {{
                min-height: 46px;
                padding: 0 14px;
                color: {PALETTE.text};
                background-color: rgba(26, 26, 46, 220);
                border: 1px solid rgba(0, 200, 83, 48);
                border-radius: 14px;
                font-family: "{ui_font_family()}";
            }}
            QComboBox#membersRoleCombo:hover,
            QComboBox#membersRoleCombo:focus {{
                border-color: rgba(0, 230, 118, 98);
                background-color: rgba(18, 18, 36, 230);
            }}
            QComboBox#membersRoleCombo::drop-down {{
                width: 28px;
                border: none;
                background: transparent;
            }}
            QComboBox#membersRoleCombo QAbstractItemView {{
                background-color: rgba(15, 15, 30, 244);
                color: {PALETTE.text};
                border: 1px solid rgba(0, 200, 83, 42);
                selection-background-color: rgba(0, 200, 83, 18);
                outline: none;
            }}
            QLabel {{
                background: transparent;
                color: {PALETTE.text};
                font-family: "{ui_font_family()}";
            }}
            QLabel#drawerSubtitle,
            QLabel#fieldLabel,
            QLabel#memberHint {{
                color: #8aa39a;
            }}
            """
        )

    def set_manage_permissions(self, can_manage_members: bool) -> None:
        self.add_member_button.setVisible(can_manage_members)

    def set_members(self, members: list[dict]) -> None:
        while self.members_rows.count():
            item = self.members_rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self.summary_label.setText(f"{len(members)} member(s) in this room.")
        if not members:
            empty_label = QLabel("No members available for this room.")
            empty_label.setObjectName("drawerSubtitle")
            self.members_rows.addWidget(empty_label)
            return

        for member in members:
            can_manage = member.get("can_set_role") or member.get("can_remove")
            row = self._create_member_row(member, can_manage)
            self.members_rows.addWidget(row)
        self.members_rows.addStretch()

    def _create_member_row(self, member: dict[str, Any], can_manage: bool) -> QFrame:
        """Create a display-only member row that is clickable if can_manage."""
        row = QFrame()
        row.setObjectName("memberRow")
        
        if can_manage:
            row.setCursor(Qt.PointingHandCursor)
        
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        # Username label
        name_label = QLabel(member.get("username", "Unknown User"))
        name_label.setFont(app_font(11, 600))
        tooltip = str(member.get("tooltip_user_id") or "").strip()
        if tooltip:
            name_label.setToolTip(tooltip)
        layout.addWidget(name_label, 1)

        # Role badge - remove "ROOM:" prefix
        role = member.get('role', '--')
        badge = StatusBadge(role, str(role).lower() or "member")
        layout.addWidget(badge, 0, Qt.AlignVCenter)

        # Member hint (Current user, Last owner, etc)
        hint = str(member.get("hint") or "").strip()
        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("memberHint")
            hint_label.setFont(app_font(9, 600))
            layout.addWidget(hint_label, 0, Qt.AlignVCenter)

        # Store member data and setup context menu behavior
        if can_manage:
            row.member_data = dict(member)
            row.mousePressEvent = lambda evt: self._on_member_row_clicked(row, evt)

        return row

    def _on_member_row_clicked(self, row: QFrame, event) -> None:
        """Handle member row click to show context menu."""
        if event.button() != Qt.LeftButton:
            return
        
        member = getattr(row, "member_data", {})
        if not member:
            return
        
        self._current_member_for_context = dict(member)
        self._show_context_menu(member, row)

    def show_members_view(self) -> None:
        self.title_label.setText("Room Members")
        self.back_button.hide()
        self.stack.setCurrentWidget(self.members_page)
        self.hide_error()

    def show_add_member_view(self) -> None:
        self.title_label.setText("Add Member")
        self.back_button.show()
        self.stack.setCurrentWidget(self.add_member_page)
        self.user_id_input.setFocus()
        self.hide_error()

    def _ensure_context_menu(self) -> MemberContextMenu:
        """Lazily create context menu on first use."""
        if self._context_menu is None:
            self._context_menu = MemberContextMenu(self)
            self._context_menu.set_role_clicked.connect(self._on_context_set_role)
            self._context_menu.remove_member_clicked.connect(self._on_context_remove)
        return self._context_menu

    def _show_context_menu(self, member: dict[str, Any], row: QFrame) -> None:
        """Show context menu for the clicked member row."""
        menu = self._ensure_context_menu()
        menu.set_actions_enabled(
            can_set_role=bool(member.get("can_set_role")),
            can_remove=bool(member.get("can_remove"))
        )
        
        # Position menu near the row
        row_global_pos = row.mapToGlobal(row.rect().topRight())
        menu_pos = QPoint(row_global_pos.x() - menu.width() - 8, row_global_pos.y())
        menu.show_at_position(menu_pos)

    def _on_context_set_role(self) -> None:
        """Handle Set Role action from context menu."""
        if self._current_member_for_context:
            self._context_menu.hide_menu()
            self.set_role_requested.emit(self._current_member_for_context)

    def _on_context_remove(self) -> None:
        """Handle Remove Member action from context menu."""
        if self._current_member_for_context:
            self._context_menu.hide_menu()
            self.remove_member_requested.emit(self._current_member_for_context)

    def _submit_add_member(self) -> None:
        user_id = self.user_id_input.text().strip()
        role = self.role_combo.currentText().strip().upper()
        if not user_id:
            self.show_error("Please enter a user ID.")
            return
        if role not in {"OWNER", "MEMBER", "VIEWER"}:
            self.show_error("Role must be OWNER, MEMBER, or VIEWER.")
            return
        self.hide_error()
        self.add_member_requested.emit(user_id, role)

    def prepare_add_member(self) -> None:
        self.user_id_input.clear()
        self.role_combo.setCurrentText("MEMBER")
        self.show_add_member_view()

    def set_add_member_loading(self, loading: bool) -> None:
        self.user_id_input.setEnabled(not loading)
        self.role_combo.setEnabled(not loading)
        self.cancel_add_button.setEnabled(not loading)
        self.submit_add_button.set_loading(loading, "Adding")

    def show_error(self, message: str) -> None:
        self.error_toast.move_to_top_center(self)
        self.error_toast.show_error(message)

    def hide_error(self) -> None:
        self.error_toast.hide_error()

    def update_anchor_geometry(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        height = max(0, parent.height() - 24)
        open_rect = QRect(parent.width() - self._drawer_width - 12, 12, self._drawer_width, height)
        closed_rect = QRect(parent.width() + 12, 12, self._drawer_width, height)
        self.setGeometry(open_rect if self._is_open else closed_rect)
        self.error_toast.move_to_top_center(self)

    def open(self) -> None:
        if self._is_open or self._animating:
            return
        self._animate(opening=True)

    def close_drawer(self) -> None:
        if not self._is_open or self._animating:
            return
        self._animate(opening=False)

    def _animate(self, opening: bool) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        height = max(0, parent.height() - 24)
        open_rect = QRect(parent.width() - self._drawer_width - 12, 12, self._drawer_width, height)
        closed_rect = QRect(parent.width() + 12, 12, self._drawer_width, height)

        self._animating = True
        self._is_open = opening
        self.show()
        self.raise_()
        self.setFocus()
        self.error_toast.raise_()

        self._animation.stop()
        self._animation.setDuration(220)
        self._animation.setEasingCurve(QEasingCurve.OutCubic if opening else QEasingCurve.InCubic)
        self._animation.setStartValue(self.geometry() if self.isVisible() else closed_rect)
        self._animation.setEndValue(open_rect if opening else closed_rect)
        self._animation.start()

    def _on_animation_finished(self) -> None:
        self._animating = False
        if not self._is_open:
            self.hide()
            self.hide_error()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.close_drawer()
            event.accept()
            return
        super().keyPressEvent(event)


__all__ = ["RoomMembersDrawer"]
