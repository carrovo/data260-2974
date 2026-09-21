import os
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates


router = APIRouter() # Create a new API router.

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR)) # Create a new Jinja2 templates.

VALID_USERNAME = os.getenv("HW3_USERNAME", "admin") # Get the valid username from the environment variables.
VALID_PASSWORD = os.getenv("HW3_PASSWORD", "password") # Get the valid password from the environment variables.

IDLE_TIMEOUT_SECONDS = int(
    os.getenv("HW3_IDLE_TIMEOUT_SECONDS", "300")
) 


def get_current_user(request: Request) -> str | None: # Get the current user.
    """
    Return the logged-in user when the session is valid.

    If the session has been idle for too long, clear it and
    treat the visitor as logged out.
    """
    user = request.session.get("user") # Get the user from the session.
    last_activity = request.session.get("last_activity") # Get the last activity from the session.

    if not user or last_activity is None:
        return None

    current_time = time.time()
    idle_time = current_time - float(last_activity)

    if idle_time > IDLE_TIMEOUT_SECONDS: # Check if the idle time is greater than the idle timeout seconds.
        request.session.clear() # Clear the session.
        return None

    request.session["last_activity"] = current_time # Set the last activity to the current time.
    return user


@router.get("/")
def home(request: Request): # Get the home page.
    user = get_current_user(request) # Get the user from the session.

    return templates.TemplateResponse( # Return the home page.
        request=request,
        name="index.html",
        context={
            "user": user,
        },
    )


@router.get("/login")
def login_page(request: Request): # Get the login page.
    user = get_current_user(request)

    if user:
        return RedirectResponse(
            url="/dashboard",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "user": None,
            "error": None,
        },
    )


@router.post("/login")
def login( # Login.
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    username_is_valid = secrets.compare_digest(
        username,
        VALID_USERNAME,
    )
    password_is_valid = secrets.compare_digest(
        password,
        VALID_PASSWORD,
    )

    if not (username_is_valid and password_is_valid):
        request.session.clear()

        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "user": None,
                "error": "Invalid username or password.",
                "entered_username": username,
            },
            status_code=401, # Return the login page with the error message.
        )

    request.session.clear()
    request.session["user"] = username
    request.session["last_activity"] = time.time()

    return RedirectResponse(
        url="/dashboard",
        status_code=303, # Redirect to the dashboard.
    )


@router.get("/dashboard")
def dashboard(request: Request):
    user = get_current_user(request)

    if not user:
        return RedirectResponse(
            url="/login?session_required=true",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user,
            "idle_timeout_seconds": IDLE_TIMEOUT_SECONDS,
        },
    )


@router.get("/logout") 
def logout(request: Request):
    request.session.clear()

    return RedirectResponse(
        url="/?logged_out=true",
        status_code=303,
    )