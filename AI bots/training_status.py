"""Replace a training status block in notebooks and terminals."""

import shutil
import sys


def _notebook_display():
    # IPython is already imported in a notebook; avoid importing it in CLI runs.
    ipython = sys.modules.get("IPython")
    shell = ipython.get_ipython() if ipython is not None else None
    if shell is not None and getattr(shell, "kernel", None) is not None:
        from IPython.display import display
        return display
    return None


class TrainingStatus:
    def __init__(self, stream=None):
        self.stream = stream
        self._display = _notebook_display() if stream is None else None
        self._handle = None
        self._line_count = 0

    def update(self, message, final=False, compact_message=None):
        if self._display is not None:
            content = {"text/plain": message}
            if self._handle is None:
                self._handle = self._display(content, raw=True, display_id=True)
            else:
                self._handle.update(content, raw=True)
            return

        stream = self.stream if self.stream is not None else sys.stdout
        if stream.isatty() and compact_message is not None:
            message = compact_message
        lines = message.splitlines() or [""]
        if stream.isatty():
            # Keep each logical row on one physical row so cursor movement stays correct.
            width = max(1, shutil.get_terminal_size(fallback=(120, 24)).columns - 1)
            for index, line in enumerate(lines):
                if len(line) <= width:
                    continue
                if width > 6:
                    prefix = (width - 3) // 3
                    lines[index] = line[:prefix] + "..." + line[-(width - prefix - 3):]
                else:
                    lines[index] = line[:width]
        # Stay on the last row between updates, then return to the top of the block.
        rewind = f"\x1b[{self._line_count - 1}A" if self._line_count > 1 else ""
        row_count = max(self._line_count, len(lines))
        lines.extend([""] * (row_count - len(lines)))
        stream.write("\r" + rewind + "\n\r".join("\x1b[2K" + line for line in lines))
        stream.flush()
        self._line_count = row_count
        if final:
            self.finish()

    def finish(self):
        """Leave the final result visible and put subsequent output on a new line."""
        if self._display is None and self._line_count:
            stream = self.stream if self.stream is not None else sys.stdout
            stream.write("\n")
            stream.flush()
            self._line_count = 0
