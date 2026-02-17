import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

"""
Mock urequests module for CalSci simulator.
Wraps Python's requests library to provide MicroPython urequests API.
"""

try:
    import requests
except ImportError:
    requests = None


class Response:
    """Mock response object compatible with urequests."""

    def __init__(self, response=None, text="", status_code=200):
        if response is not None:
            self._response = response
            self.status_code = response.status_code
            self._text = response.text
            self._content = response.content
        else:
            self._response = None
            self.status_code = status_code
            self._text = text
            self._content = text.encode('utf-8')

    @property
    def text(self):
        return self._text

    @property
    def content(self):
        return self._content

    def json(self):
        if self._response is not None:
            return self._response.json()
        import json
        return json.loads(self._text)

    def close(self):
        """Close the response (no-op in mock)."""
        pass


def get(url, headers=None, timeout=10):
    """Perform HTTP GET request."""
    if requests is None:
        return Response(text="requests module not installed", status_code=500)

    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        return Response(response=resp)
    except requests.exceptions.ConnectionError:
        return Response(text="Connection error", status_code=0)
    except requests.exceptions.Timeout:
        return Response(text="Timeout", status_code=0)
    except Exception as e:
        return Response(text=str(e), status_code=0)


def post(url, data=None, json=None, headers=None, timeout=10):
    """Perform HTTP POST request."""
    if requests is None:
        return Response(text="requests module not installed", status_code=500)

    try:
        resp = requests.post(url, data=data, json=json, headers=headers, timeout=timeout)
        return Response(response=resp)
    except requests.exceptions.ConnectionError:
        return Response(text="Connection error", status_code=0)
    except requests.exceptions.Timeout:
        return Response(text="Timeout", status_code=0)
    except Exception as e:
        return Response(text=str(e), status_code=0)


def put(url, data=None, json=None, headers=None, timeout=10):
    """Perform HTTP PUT request."""
    if requests is None:
        return Response(text="requests module not installed", status_code=500)

    try:
        resp = requests.put(url, data=data, json=json, headers=headers, timeout=timeout)
        return Response(response=resp)
    except requests.exceptions.ConnectionError:
        return Response(text="Connection error", status_code=0)
    except requests.exceptions.Timeout:
        return Response(text="Timeout", status_code=0)
    except Exception as e:
        return Response(text=str(e), status_code=0)


def delete(url, headers=None, timeout=10):
    """Perform HTTP DELETE request."""
    if requests is None:
        return Response(text="requests module not installed", status_code=500)

    try:
        resp = requests.delete(url, headers=headers, timeout=timeout)
        return Response(response=resp)
    except requests.exceptions.ConnectionError:
        return Response(text="Connection error", status_code=0)
    except requests.exceptions.Timeout:
        return Response(text="Timeout", status_code=0)
    except Exception as e:
        return Response(text=str(e), status_code=0)
