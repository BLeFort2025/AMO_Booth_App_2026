# Farm Tax Calculator — Developer's Manual

> **Location:** `app/farm_tax/DEVELOPERS_MANUAL.md`
> This manual serves as the primary technical documentation for the Farm Tax Calculator module (Page 11).

## System Architecture Overview

The Farm Tax Calculator is a revenue-neutral tax simulation engine that computes property tax shifts under varying farm tax ratio scenarios. 

**Key Components:**
- **Entry Point:** `app/pages/11_🌾_Farm_Tax_Calculator.py` (The standalone Streamlit page)
- **Core Visuals:** `app/farm_tax/farm_tax_story.py` (Generates charts, UI, and dynamic narratives)
- **Reporting Engine:** `app/farm_tax/farm_tax_report.py` (Automated Word & PowerPoint generation)
- **Provincial Simulation:** `app/farm_tax/provincial_simulator.py` (For province-wide aggregations)

## URL Parameters & App Routing

As an embedded dashboard tool, the Farm Tax Calculator is often shared directly with external stakeholders or field staff who do not need access to the broader OFA economic dataset. 

To facilitate this, we have implemented custom URL parameters that lock down the application UI.

### 1. Standalone Mode (Recommended for OFA Field Staff)

By appending `?standalone=true` to the URL, the calculator hides the overall Streamlit page navigation list and the top app header, preventing the user from navigating to other modules, while **retaining** the sidebar for the "Select Municipality" dropdown list. 

**Usage:**
`https://farmfinancedatabase-qdaadnipzfsrzqfh5yvwaz.streamlit.app/Farm_Tax_Calculator?standalone=true`

**Implementation Details:**
In `11_🌾_Farm_Tax_Calculator.py`, we use robust client-side JavaScript injection (`components.html`) to forcefully apply the necessary CSS styling directly from the browser context, completely bypassing any internal Streamlit backend routing bugs:
```python
import streamlit.components.v1 as components

components.html(
    \"\"\"
    <script>
        const urlParams = new URLSearchParams(window.parent.location.search);
        if (urlParams.get('standalone') === 'true') {
            const style = window.parent.document.createElement('style');
            style.innerHTML = `
                /* Broadly hide the page navigation list */
                [data-testid="stSidebarNav"] { display: none !important; }
                div[data-testid="stSidebarNav"] { display: none !important; }
                /* Hide header */
                header[data-testid="stHeader"] { display: none !important; }
                .block-container { padding-top: 2rem !important; }
            `;
            window.parent.document.head.appendChild(style);
        }
    </script>
    \"\"\",
    height=0, width=0,
)
```

### 2. Full Embed Mode (Standard Streamlit)

For embedding the calculator within an iFrame on another site, or for locking it down completely where you don't even want them to use the sidebar, you can use Streamlit's native `?embed=true` parameter.

**Usage:**
`https://farmfinancedatabase-qdaadnipzfsrzqfh5yvwaz.streamlit.app/Farm_Tax_Calculator?embed=true`

*Note: This will hide the entire sidebar completely, so users will not be able to select a new municipality through the sidebar dropdown.*

### 3. Full App Mode (Default)

If the dashboard is accessed without any URL parameters, the calculator loads normally inside the multi-page application with all navigation elements visible.

**Usage:**
`https://farmfinancedatabase-qdaadnipzfsrzqfh5yvwaz.streamlit.app/Farm_Tax_Calculator`

## Development Roadmap
See `app/farm_tax/ROADMAP.md` for upcoming feature improvements, completed tasks, and integration pipelines.
