import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile


@dataclass(frozen=True, slots=True)
class UploadedWorkbook:
    directory: Path
    input_path: Path
    output_path: Path
    filename: str

    @classmethod
    async def create(cls, upload: UploadFile) -> "UploadedWorkbook":
        filename = Path(upload.filename or "").name
        if not filename or Path(filename).suffix.casefold() != ".xlsx":
            await upload.close()
            raise ValueError("Ожидается файл с расширением .xlsx")

        directory = Path(tempfile.mkdtemp(prefix="define-sellers-"))
        input_path = directory / "input" / filename
        output_path = directory / "output" / filename
        input_path.parent.mkdir()
        output_path.parent.mkdir()

        try:
            with input_path.open("wb") as target:
                while chunk := await upload.read(1024 * 1024):
                    target.write(chunk)
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        finally:
            await upload.close()

        return cls(directory, input_path, output_path, filename)

    def cleanup(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)
