# Scientific Calculator Apps

These apps implement **scientific and matrix‑based tools** used by the calculator. Most of them present a form to collect inputs and then render results on the display.

## Apps

- **`add_matrices.py`** – Add matrices.
- **`constants.py`** – Built‑in scientific constants lookup.
- **`determinant.py`** – Determinant calculator.
- **`eigen_values.py`** – Eigenvalue solver.
- **`graph.py`** – Graph plotting tool with cursor + toolbox (`Area`, `Tangent`, `Normal`).
- **`lu_decomposition.py`** – LU decomposition.
- **`matrix_inverse.py`** – Matrix inverse solver.
- **`matrix_mul_2.py`** – Matrix multiplication.
- **`matrix_operations.py`** – Menu for matrix operations.
- **`mymolecule.py`** – Molecule‑related calculations (custom tool).
- **`qr_decomposition.py`** – QR decomposition.
- **`quad_eqn_sol.py`** – Quadratic equation solver.
- **`rank.py`** – Matrix rank.
- **`reduced_row_echelon.py`** – RREF solver.
- **`row_echelon_form.py`** – Row‑echelon form.
- **`simultanious_eqn_sol.py`** – Simultaneous equation solver.
- **`transpose.py`** – Matrix transpose.

## How to use

Open **Scientific Calculator** from the root menu and select a tool. Most screens:
- use the `form` buffer for inputs,
- update with `form.update_buffer(...)`,
- render via `form_refresh.refresh(state=nav.current_state())`.

## Graph Tool (`graph.py`)

### Base controls

- Press `ok` from the graph form to render the function.
- Press `+` / `-` to zoom in/out.
- With cursor OFF, use `nav_u` / `nav_d` / `nav_l` / `nav_r` to pan.
- Press `a` (or `A`) to toggle cursor mode.
- In cursor mode, `nav_u` / `nav_d` also pan the graph (except when selected tool is `Area`, where they switch boundary focus).

### Toolbox controls

- Press `toolbox` to open the graph tools menu.
- Menu items:
  - `Area`: two-cursor area-under-curve mode with shaded region and computed area.
  - `Tangent`: tangent line at selected x-value.
  - `Normal`: normal line at selected x-value.
- In the menu, use `nav_u` / `nav_d` to move selection and `ok` to add a new tool instance.
- Re-opening toolbox lets you add more tools at any time.
- Selecting the same tool multiple times is allowed (`Tangent`, `Normal`, etc. can be added more than once).

### Used tools list

- Press `,` (comma key) to open the active tools list.
- The list shows numbered tools (`A1`, `T2`, `N1`, ...) with current x-pixel position (`px`).
- Use `nav_u` / `nav_d` to pick a row.
- Press `ok` to select that tool for cursor editing.
- Press `AC` (or `nav_b` / `-`) to remove the selected tool.

### Area mode controls

- `nav_u`: focus left boundary.
- `nav_d`: focus right boundary.
- `nav_l` / `nav_r`: move focused boundary.

### Locked x-value behavior

When graph features are active (`Area`, `Tangent`, `Normal`), each tool stores its own math-space x-values, not only screen pixels.  
This means zoom and pan do not change selected x-values or area interval endpoints; only their screen positions are remapped.
