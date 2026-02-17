import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import ntptime
import time as systime
from data_modules.object_handler import nav, keypad_state_manager, typer, display, app, menu, menu_refresh

def get_indian_time():
    """Get time using NTP and convert to IST (UTC+5:30)"""
    try:
        # Set time using NTP
        ntptime.settime()
        
        # Get current UTC time
        current_time = systime.localtime()
        
        # Extract components: (year, month, day, hour, minute, second, weekday, yearday)
        year, month, day, hour, minute, second, weekday, yearday = current_time
        
        # Convert UTC to IST (add 5 hours 30 minutes)
        minute += 30
        hour += 5
        
        # Handle minute overflow
        if minute >= 60:
            minute -= 60
            hour += 1
        
        # Handle hour overflow
        if hour >= 24:
            hour -= 24
            day += 1
            weekday = (weekday + 1) % 7
            yearday += 1
            
            # Handle month overflow (simplified)
            days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
            if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
                days_in_month[1] = 29  # Leap year
            
            if day > days_in_month[month - 1]:
                day = 1
                month += 1
                if month > 12:
                    month = 1
                    year += 1
        
        # Convert to 12-hour format with AM/PM
        if hour == 0:
            hour_12 = 12
            period = "AM"
        elif hour < 12:
            hour_12 = hour
            period = "AM"
        elif hour == 12:
            hour_12 = 12
            period = "PM"
        else:
            hour_12 = hour - 12
            period = "PM"
        
        # Format date: day, month, year
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        date_str = f"{day:02d}, {month_names[month-1]}, {year}"
        
        # Format time: HH:MM:SS AM/PM
        time_str = f"{hour_12:02d}:{minute:02d}:{second:02d} {period}"
        
        return {
            'success': True,
            'date': date_str,
            'time': time_str,
            'day_of_week': weekday,
            'day_of_year': yearday
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)[:15]}

def format_day_of_week(day_num):
    """Convert day number to day name"""
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    if isinstance(day_num, int) and 0 <= day_num <= 6:
        return days[day_num]
    return 'N/A'

def utc_time():
    """Main Indian time app using NTP"""
    display.clear_display()
    
    menu.menu_list = ["Indian Time", "Getting time...", "Please wait"]
    menu.update()
    menu_refresh.refresh()
    
    try:
        while True:
            # Fetch time via NTP
            result = get_indian_time()
            
            if result['success']:
                day_name = format_day_of_week(result.get('day_of_week'))
                
                menu.menu_list = [
                    "Indian Time (IST)",
                    f"Date: {result['date']}",
                    f"Time: {result['time']}",
                    f"Day: {day_name}",
                    f"Day of year: {result['day_of_year']}",
                    "",
                    "Press OK to refresh"
                ]
            else:
                error_msg = result.get('error', 'Unknown')
                menu.menu_list = [
                    "Indian Time",
                    "NTP error:",
                    error_msg,
                    "Check WiFi",
                    "",
                    "Press OK to retry"
                ]
            
            menu.update()
            display.clear_display()
            menu_refresh.refresh()
            
            # Wait for user input
            while True:
                inp = typer.start_typing()
                
                if inp == "back":
                    app.set_app_name("installed_apps")
                    app.set_group_name("root")
                    return
                
                elif inp == "ok":
                    menu.menu_list = ["Indian Time", "Refreshing...", ""]
                    menu.update()
                    display.clear_display()
                    menu_refresh.refresh()
                    break
                
                elif inp == "alpha" or inp == "beta":
                    keypad_state_manager(x=inp)
                    menu.update_buffer("")
                
                menu.update_buffer(inp)
                menu_refresh.refresh(state=nav.current_state())
                
    except Exception as e:
        print(f"Error: {e}")
        app.set_app_name("installed_apps")
        app.set_group_name("root")
