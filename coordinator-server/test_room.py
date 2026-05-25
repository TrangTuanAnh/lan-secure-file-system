"""Integration tests for room management module."""
import pytest
import uuid
from datetime import datetime, timezone
from database import Database
from config import load_config
from room.room_service import RoomService
from audit.audit_service import AuditService
from notification.notification_service import NotificationService
from db_test_utils import cleanup_database


@pytest.fixture
def db():
    """Create database connection for tests."""
    config = load_config()
    database = Database(config.database)
    database.connect()
    cleanup_database(database)
    try:
        yield database
    finally:
        cleanup_database(database)
        database.close()


@pytest.fixture
def audit_service(db):
    """Create audit service for tests."""
    return AuditService(db)


@pytest.fixture
def notification_service():
    """Create notification service for tests."""
    return NotificationService()


@pytest.fixture
def room_service(db, audit_service, notification_service):
    """Create room service for tests."""
    return RoomService(db, audit_service, notification_service)


@pytest.fixture
def admin_user(db):
    """Create an ADMIN user for tests."""
    user_id = str(uuid.uuid4())
    username = f"admin_{uuid.uuid4().hex[:8]}"
    email = f"{username}@test.com"
    now = datetime.now(timezone.utc)
    
    db.execute_update(
        """
        INSERT INTO users (id, username, email, password_hash, global_role, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, username, email, "dummy_hash", "ADMIN", now, now)
    )
    
    yield {"id": user_id, "username": username, "email": email, "global_role": "ADMIN"}
    cleanup_database(db)


@pytest.fixture
def regular_user(db):
    """Create a regular USER for tests."""
    user_id = str(uuid.uuid4())
    username = f"user_{uuid.uuid4().hex[:8]}"
    email = f"{username}@test.com"
    now = datetime.now(timezone.utc)
    
    db.execute_update(
        """
        INSERT INTO users (id, username, email, password_hash, global_role, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, username, email, "dummy_hash", "USER", now, now)
    )
    
    yield {"id": user_id, "username": username, "email": email, "global_role": "USER"}
    cleanup_database(db)


def test_create_room_as_admin(room_service, admin_user):
    """Test creating a room as ADMIN user."""
    success, room_data, error_code = room_service.create_room(
        admin_user["id"],
        admin_user["global_role"],
        "Test Room"
    )
    
    assert success is True
    assert error_code is None
    assert room_data is not None
    assert room_data["name"] == "Test Room"
    assert room_data["createdBy"] == admin_user["id"]
    assert "roomId" in room_data


def test_create_room_as_regular_user(room_service, regular_user):
    """Test creating a room as regular USER (should fail)."""
    success, room_data, error_code = room_service.create_room(
        regular_user["id"],
        regular_user["global_role"],
        "Test Room"
    )
    
    assert success is False
    assert error_code == "PERMISSION_DENIED"
    assert room_data is None


def test_add_member_to_room(room_service, admin_user, regular_user):
    """Test adding a member to a room."""
    # Create room
    success, room_data, _ = room_service.create_room(
        admin_user["id"],
        admin_user["global_role"],
        "Test Room"
    )
    assert success is True
    room_id = room_data["roomId"]
    
    # Add member
    success, error_code = room_service.add_member(
        admin_user["id"],
        admin_user["global_role"],
        room_id,
        regular_user["id"],
        "MEMBER"
    )
    
    assert success is True
    assert error_code is None


def test_add_duplicate_member(room_service, admin_user, regular_user):
    """Test adding a member who is already in the room."""
    # Create room
    success, room_data, _ = room_service.create_room(
        admin_user["id"],
        admin_user["global_role"],
        "Test Room"
    )
    room_id = room_data["roomId"]
    
    # Add member first time
    room_service.add_member(
        admin_user["id"],
        admin_user["global_role"],
        room_id,
        regular_user["id"],
        "MEMBER"
    )
    
    # Try to add same member again
    success, error_code = room_service.add_member(
        admin_user["id"],
        admin_user["global_role"],
        room_id,
        regular_user["id"],
        "MEMBER"
    )
    
    assert success is False
    assert error_code == "ALREADY_MEMBER"


def test_remove_member_from_room(room_service, admin_user, regular_user):
    """Test removing a member from a room."""
    # Create room and add member
    success, room_data, _ = room_service.create_room(
        admin_user["id"],
        admin_user["global_role"],
        "Test Room"
    )
    room_id = room_data["roomId"]
    
    room_service.add_member(
        admin_user["id"],
        admin_user["global_role"],
        room_id,
        regular_user["id"],
        "MEMBER"
    )
    
    # Remove member
    success, error_code = room_service.remove_member(
        admin_user["id"],
        admin_user["global_role"],
        room_id,
        regular_user["id"]
    )
    
    assert success is True
    assert error_code is None


def test_cannot_remove_last_owner(room_service, admin_user):
    """Test that the last OWNER cannot be removed from a room."""
    # Create room (admin becomes OWNER)
    success, room_data, _ = room_service.create_room(
        admin_user["id"],
        admin_user["global_role"],
        "Test Room"
    )
    room_id = room_data["roomId"]
    
    # Try to remove the only OWNER
    success, error_code = room_service.remove_member(
        admin_user["id"],
        admin_user["global_role"],
        room_id,
        admin_user["id"]
    )
    
    assert success is False
    assert error_code == "CANNOT_REMOVE_LAST_OWNER"


def test_set_role(room_service, admin_user, regular_user):
    """Test changing a member's role."""
    # Create room and add member
    success, room_data, _ = room_service.create_room(
        admin_user["id"],
        admin_user["global_role"],
        "Test Room"
    )
    room_id = room_data["roomId"]
    
    room_service.add_member(
        admin_user["id"],
        admin_user["global_role"],
        room_id,
        regular_user["id"],
        "VIEWER"
    )
    
    # Change role to MEMBER
    success, error_code = room_service.set_role(
        admin_user["id"],
        admin_user["global_role"],
        room_id,
        regular_user["id"],
        "MEMBER"
    )
    
    assert success is True
    assert error_code is None


def test_cannot_change_own_role(room_service, admin_user):
    """Test that a user cannot change their own role."""
    # Create room
    success, room_data, _ = room_service.create_room(
        admin_user["id"],
        admin_user["global_role"],
        "Test Room"
    )
    room_id = room_data["roomId"]
    
    # Try to change own role
    success, error_code = room_service.set_role(
        admin_user["id"],
        admin_user["global_role"],
        room_id,
        admin_user["id"],
        "VIEWER"
    )
    
    assert success is False
    assert error_code == "CANNOT_CHANGE_OWN_ROLE"


def test_list_rooms_as_admin(room_service, admin_user):
    """Test listing rooms as ADMIN (should see all rooms)."""
    # Create a room
    room_service.create_room(
        admin_user["id"],
        admin_user["global_role"],
        "Test Room 1"
    )
    
    # List rooms
    success, rooms_list, error_code = room_service.list_rooms(
        admin_user["id"],
        admin_user["global_role"]
    )
    
    assert success is True
    assert error_code is None
    assert len(rooms_list) >= 1
    assert any(room["name"] == "Test Room 1" for room in rooms_list)


def test_list_rooms_as_regular_user(room_service, admin_user, regular_user):
    """Test listing rooms as regular user (should only see rooms they're in)."""
    # Create room and add regular user
    success, room_data, _ = room_service.create_room(
        admin_user["id"],
        admin_user["global_role"],
        "Test Room"
    )
    room_id = room_data["roomId"]
    
    room_service.add_member(
        admin_user["id"],
        admin_user["global_role"],
        room_id,
        regular_user["id"],
        "MEMBER"
    )
    
    # List rooms as regular user
    success, rooms_list, error_code = room_service.list_rooms(
        regular_user["id"],
        regular_user["global_role"]
    )
    
    assert success is True
    assert error_code is None
    assert len(rooms_list) >= 1
    assert any(room["roomId"] == room_id for room in rooms_list)


def test_list_members(room_service, admin_user, regular_user):
    """Test listing members of a room."""
    # Create room and add member
    success, room_data, _ = room_service.create_room(
        admin_user["id"],
        admin_user["global_role"],
        "Test Room"
    )
    room_id = room_data["roomId"]
    
    room_service.add_member(
        admin_user["id"],
        admin_user["global_role"],
        room_id,
        regular_user["id"],
        "MEMBER"
    )
    
    # List members
    success, members_list, error_code = room_service.list_members(
        admin_user["id"],
        admin_user["global_role"],
        room_id
    )
    
    assert success is True
    assert error_code is None
    assert len(members_list) == 2  # Admin (OWNER) and regular user (MEMBER)
    
    # Check that both users are in the list
    user_ids = [member["userId"] for member in members_list]
    assert admin_user["id"] in user_ids
    assert regular_user["id"] in user_ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
