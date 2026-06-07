"""
Tool definitions for the LLM function-calling interface.

These are the tools the LLM can invoke based on user messages.
Each tool maps to a function in the analysis engine.
"""

# Tools wired into the Anthropic Messages API. Shape matches
# https://docs.anthropic.com/en/api/messages#body-tools
ANTHROPIC_TOOLS = [
    {
        "name": "list_datalogs",
        "description": (
            "List every lab data log with its extracted metadata (material, "
            "date, sample names, scan types, summary, keywords). Use this when "
            "the user asks broad questions about what data exists, or when you "
            "need to pick which specific files to read for a question. The "
            "system prompt already contains the current index, so usually you "
            "only need this if the user asks for a refresh."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "read_datalog",
        "description": (
            "Read the full contents of one data log file (Excel parsed to "
            "markdown tables, PDFs inlined as documents, text files as text). "
            "Use this after consulting the data-log index when you need actual "
            "numbers or details to answer a user question. Prefer reading one "
            "or two clearly-relevant files over many — readings cost tokens."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "Exact filename from the data-log index, e.g. "
                        "'2026-05-25_TTS2_log.xlsx'."
                    ),
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "trarpes_open",
        "description": (
            "Open the interactive TR-ARPES analysis widget in the chat. Use this "
            "whenever the user wants to compare two ARPES scans, compute a "
            "pump-probe differential (B - A), inspect EDCs, or otherwise work "
            "with .pxt files. If the user names specific scan numbers (e.g. "
            "'compare scan 30 and 31'), pass them as scan_a and scan_b — "
            "otherwise leave both null and let the user pick in the widget."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scan_a": {
                    "type": ["integer", "null"],
                    "description": "Reference (pump-off or earlier-delay) scan number, e.g. 30 for scan_030.pxt.",
                },
                "scan_b": {
                    "type": ["integer", "null"],
                    "description": "Pumped (later-delay) scan number to subtract the reference from.",
                },
            },
            "required": [],
        },
    },
]


TOOLS = [
    {
        "name": "load_pxt",
        "description": "Load a .pxt file from a Scienta hemispherical analyzer and return an xarray DataArray.",
        "parameters": {
            "filepath": {"type": "string", "description": "Path to the .pxt file"},
        },
    },
    {
        "name": "plot_band_structure",
        "description": "Generate a 2D intensity map (energy x emission angle) from ARPES data.",
        "parameters": {
            "filepath": {"type": "string", "description": "Path to the .pxt file"},
            "energy_range": {
                "type": "array",
                "description": "Optional [min, max] energy range in eV",
            },
            "colormap": {
                "type": "string",
                "description": "Matplotlib colormap name",
                "default": "viridis",
            },
            "smoothing": {
                "type": "number",
                "description": "Gaussian smoothing sigma",
                "default": 0,
            },
        },
    },
    {
        "name": "compute_differential",
        "description": "Compute the differential map by subtracting a reference scan from a pumped scan.",
        "parameters": {
            "reference_path": {
                "type": "string",
                "description": "Path to reference (pump-off) .pxt file",
            },
            "pumped_path": {
                "type": "string",
                "description": "Path to pumped .pxt file",
            },
        },
    },
    {
        "name": "plot_differential",
        "description": "Generate a red/white/blue differential map from pump-probe subtraction.",
        "parameters": {
            "reference_path": {"type": "string"},
            "pumped_path": {"type": "string"},
            "colormap": {"type": "string", "default": "RdBu_r"},
            "energy_range": {"type": "array"},
            "symmetric_clim": {
                "type": "boolean",
                "description": "Force symmetric color limits",
                "default": True,
            },
        },
    },
    {
        "name": "extract_metadata",
        "description": "Extract metadata from a .pxt file header (delay stage position, temperature, etc.).",
        "parameters": {
            "filepath": {"type": "string", "description": "Path to the .pxt file"},
        },
    },
    {
        "name": "lookup_material",
        "description": "Look up properties of a material (lattice constants, band gap, space group, etc.).",
        "parameters": {
            "material_name": {
                "type": "string",
                "description": "Material name or chemical formula",
            },
        },
    },
]
