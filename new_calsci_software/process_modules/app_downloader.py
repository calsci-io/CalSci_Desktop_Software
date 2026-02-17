import st7565 as display

try:
    import tools
    if hasattr(display, "graphics") and not hasattr(display.graphics, "pixels_changed"):
        display.graphics = tools.refresh(display.graphics, pixels_changed=200)
except Exception:
    pass

# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

import requests
from tinydb import TinyDB, Query
import machine
class Apps():
    def __init__(self):
        self.db = TinyDB("db/installed_apps.json")
        self.app_query = Query()

    def insert(self, app_name, group_name="installed_apps"):
        self.db.insert({"app_name": app_name, "group_name": group_name})
        return True

    def search_app_name(self, app_name, group_name="installed_apps"):
        result = self.db.search(
            (self.app_query.app_name == app_name)
            & (self.app_query.group_name == group_name)
        )
        if len(result) == 0:
            return None
        return result

    def sea_by_g(self, group_name):
        return self.db.search(self.app_query.group_name == group_name)

    def get_group_apps(self, group_name="installed_apps"):
        res = self.sea_by_g(group_name)
        app_list = []
        for app in res:
            app_list.append(app["app_name"])
        return app_list
    
    def insert_new_app(self, app_name, group_name="installed_apps"): #insert new app
        app=self.search_app_name(app_name)
        if app == None:
            self.insert(app_name, group_name)
            return True
        return False

    def delete_app(self, app_name, group_name="installed_apps"):
        app = self.search_app_name(app_name)
        if app is None:
            return False
        self.db.remove(
            (self.app_query.app_name == app_name)
            & (self.app_query.group_name == group_name)
        )
        return True

class App_downloader:
    def __init__(self):
        self.apps = Apps()
        self.mac=''.join('{:02X}'.format(b) for b in machine.unique_id())
        self.app_name=""
    def check_status(self): #1. req 1
        check_status_url = "https://czxnvqwbwszzfgecpkbi.supabase.co/functions/v1/check-pending-apps?macAddress="+self.mac                    ###################### needs to be edited
        r=requests.get(check_status_url)
        res=r.json()
        print(res)
        if res["response"]=="true":
            return True
        else:
            return False


    def download_app(self): #2. req 2
        
        download_url = f"https://czxnvqwbwszzfgecpkbi.supabase.co/functions/v1/get-pending-apps?macAddress={self.mac}"              ##################### needs to be edited
        r = requests.get(str(download_url))
        
        res=r.json()
        print(res)
        self.app_name = res["app_name"]
        with open(f"/apps/installed_apps/{self.app_name}.py", "w") as app_file:
            app_file.write(res["code"])
        return True
    
    
    def update_app_list(self): #3. db operation
        self.apps.insert_new_app(self.app_name)
        return True

    def send_confirmation(self): #4. req 3
        confirmation_url = f"https://czxnvqwbwszzfgecpkbi.supabase.co/functions/v1/confirm-download?macAddress={self.mac}"                ################# needs to be edited 
        r = requests.get(str(confirmation_url))
        res=r.json()
        print(res)
        return True

    def reset(self):
        from machine import reset
        reset()
        return True
