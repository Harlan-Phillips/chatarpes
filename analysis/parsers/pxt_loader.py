"""
.pxt file loader for Scienta hemispherical analyzer data.

TODO from lab lead:
- [ ] Sample .pxt files to reverse-engineer or confirm format
- [ ] Confirm if using PyARPES built-in loader, igorpy, or custom parser
- [ ] Document header format and metadata fields
"""


def load_pxt(filepath: str):
    """
    Load a .pxt file and return structured data.

    .pxt files are Igor Pro binary wave files exported by Scienta analyzers.
    They contain 2D data (energy x angle) plus metadata in the header.

    PLACEHOLDER: Implementation depends on sample files from lab lead.
    """
    raise NotImplementedError(
        "Awaiting sample .pxt files. See docs/placeholders/NEEDED_FROM_LAB.md"
    )


def parse_pxt_header(filepath: str) -> dict:
    """
    Parse metadata from .pxt file header without loading full data.

    Expected fields (to be confirmed with actual files):
    - delay_stage_position
    - temperature
    - photon_energy
    - pass_energy
    - slit_width
    - acquisition_mode
    - timestamp
    """
    raise NotImplementedError("Awaiting sample .pxt files")
