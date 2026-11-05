"""Asynchronous XDG Desktop Portal wallpaper requests.

The portal's SetWallpaperFile method uses Unix FD passing because local file
URIs are not accepted by SetWallpaperURI.
"""

import os
import uuid


BUS_NAME = "org.freedesktop.portal.Desktop"
OBJECT_PATH = "/org/freedesktop/portal/desktop"
WALLPAPER_INTERFACE = "org.freedesktop.portal.Wallpaper"
REQUEST_INTERFACE = "org.freedesktop.portal.Request"

_PORTAL_UNAVAILABLE_ERRORS = {
    "org.freedesktop.DBus.Error.ServiceUnknown",
    "org.freedesktop.DBus.Error.NameHasNoOwner",
    "org.freedesktop.DBus.Error.UnknownInterface",
    "org.freedesktop.DBus.Error.UnknownMethod",
    "org.freedesktop.DBus.Error.UnknownObject",
    "org.freedesktop.DBus.Error.NoReply",
    "org.freedesktop.DBus.Error.NotSupported",
}


def is_portal_unavailable_error(error_name):
    """Return whether a D-Bus error means this portal cannot be used."""
    return error_name in _PORTAL_UNAVAILABLE_ERRORS


def portal_response_result(response_code):
    """Translate the standard Request.Response code into a result/message."""
    if response_code == 0:
        return True, None
    if response_code == 1:
        return False, "The wallpaper change was cancelled in the desktop portal."
    if response_code == 2:
        return False, "The desktop portal could not set the wallpaper."
    return False, f"The desktop portal returned an unknown response ({response_code})."


def request_wallpaper(path, callback):
    """Request a wallpaper change; callback receives (result, message).

    result is True on success, False on user cancellation/error, and None when
    the portal is unavailable and the caller should use its existing fallback.
    """
    from gi.repository import Gio, GLib

    fd = None
    connection = None
    subscription_id = None
    state = {"completed": False, "callback": callback}

    def finish(result, message=None):
        if state["completed"]:
            return
        state["completed"] = True
        if connection is not None and subscription_id is not None:
            connection.signal_unsubscribe(subscription_id)
        callback(result, message)

    def on_response(
        _connection, _sender_name, _object_path, _interface_name,
        _signal_name, parameters, _user_data
    ):
        response_code, _results = parameters.unpack()
        result, message = portal_response_result(response_code)
        finish(result, message)

    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
        try:
            connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error as error:
            finish(None, error.message)
            return
        unique_name = connection.get_unique_name()
        if not unique_name:
            finish(None, "No session-bus identity is available for the wallpaper portal.")
            return
        sender = unique_name.lstrip(":").replace(".", "_")
        token = f"wallmat_{uuid.uuid4().hex}"
        expected_handle = (
            f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
        )
        subscription_id = connection.signal_subscribe(
            BUS_NAME,
            REQUEST_INTERFACE,
            "Response",
            expected_handle,
            None,
            Gio.DBusSignalFlags.NONE,
            on_response,
            None,
        )

        fd_list = Gio.UnixFDList.new()
        handle = fd_list.append(fd)
        options = {
            "show-preview": GLib.Variant("b", True),
            "set-on": GLib.Variant("s", "background"),
            "handle_token": GLib.Variant("s", token),
        }
        parameters = GLib.Variant("(sha{sv})", ("", handle, options))
        state["fd_list"] = fd_list

        def on_method_finished(bus, result, _user_data):
            nonlocal subscription_id
            try:
                reply, _returned_fds = bus.call_with_unix_fd_list_finish(result)
                actual_handle = reply.unpack()[0]
                if actual_handle != expected_handle and not state["completed"]:
                    connection.signal_unsubscribe(subscription_id)
                    subscription_id = connection.signal_subscribe(
                        BUS_NAME,
                        REQUEST_INTERFACE,
                        "Response",
                        actual_handle,
                        None,
                        Gio.DBusSignalFlags.NONE,
                        on_response,
                        None,
                    )
            except GLib.Error as error:
                remote_name = Gio.DBusError.get_remote_error(error) or ""
                if is_portal_unavailable_error(remote_name):
                    finish(None, error.message)
                else:
                    finish(False, error.message)

        connection.call_with_unix_fd_list(
            BUS_NAME,
            OBJECT_PATH,
            WALLPAPER_INTERFACE,
            "SetWallpaperFile",
            parameters,
            GLib.VariantType.new("(o)"),
            Gio.DBusCallFlags.NONE,
            5000,
            fd_list,
            None,
            on_method_finished,
            None,
        )
    except GLib.Error as error:
        remote_name = Gio.DBusError.get_remote_error(error) or ""
        if is_portal_unavailable_error(remote_name):
            finish(None, error.message)
        else:
            finish(False, error.message)
    except (AttributeError, TypeError) as error:
        finish(None, str(error))
    except OSError as error:
        finish(False, str(error))
    finally:
        if fd is not None:
            os.close(fd)
