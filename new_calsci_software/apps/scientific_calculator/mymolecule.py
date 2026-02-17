# Copyright (c) 2025 CalSci
# Licensed under the MIT License.

from data_modules.object_handler import display, form, nav, form_refresh, typer, keypad_state_manager, keypad_state_manager_reset, app
import urequests
import gc
import time
import json

def mymolecule(db={}):
    print("start of mymolecule", gc.mem_free())
    keypad_state_manager_reset()
    
    display.clear_display()
    form.input_list={"inp_0": "glucose"}
    form.form_list=["enter compound:", "inp_0"]
    form.update()
    form_refresh.refresh()
    
    while True:
        inp = typer.start_typing()
        
        if inp == "back":
            app.set_app_name("scientific_calculator")
            app.set_group_name("root")
            break
        elif inp == "ok":
            # Show loading
            form.form_list=["enter compound:", "inp_0", "loading..."]
            form.update()
            form_refresh.refresh()
            
            molecule = form.inp_list()["inp_0"].strip()
            
            # PubChem API endpoint
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{molecule}/property/MolecularFormula,MolecularWeight,IUPACName/JSON"
            
            try:
                response = urequests.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    response.close()
                    
                    # Extract data
                    props = data["PropertyTable"]["Properties"][0]
                    formula = props.get("MolecularFormula", "N/A")
                    weight = props.get("MolecularWeight", "N/A")
                    iupac = props.get("IUPACName", "N/A")
                    
                    # Split IUPAC name into lines of exactly 21 characters
                    iupac_lines = []
                    if len(iupac) > 15:  # "IUPAC: " takes 7 chars, so 21-7=14 for first line
                        # First line: "IUPAC: " + 14 chars
                        iupac_lines.append(f"IUPAC: {iupac[:14]}")
                        remaining = iupac[14:]
                        
                        # Subsequent lines: 21 chars each
                        while len(remaining) > 0:
                            iupac_lines.append(remaining[:21])
                            remaining = remaining[21:]
                    else:
                        iupac_lines = [f"IUPAC: {iupac}"]
                    
                    # Display results
                    display.clear_display()
                    form.form_list = [
                        "enter compound:",
                        "inp_0",
                        f"Formula: {formula}",
                        f"Weight: {weight}"
                    ] + iupac_lines
                    
                    form.update()
                    form_refresh.refresh()
                else:
                    response.close()
                    display.clear_display()
                    form.form_list = [
                        "enter compound:",
                        "inp_0",
                        "Compound not found"
                    ]
                    form.update()
                    form_refresh.refresh()
                    
            except Exception as e:
                print(f"Error: {e}")
                display.clear_display()
                form.form_list = [
                    "enter compound:",
                    "inp_0",
                    "Check WiFi connection"
                ]
                form.update()
                form_refresh.refresh()
                
        elif inp == "alpha" or inp == "beta":
            keypad_state_manager(x=inp)
            form.update_buffer("")
            
        elif inp not in ["alpha", "beta", "ok"]:
            form.update_buffer(inp)
            
        form_refresh.refresh(state=nav.current_state())
        time.sleep(0.1)     
        