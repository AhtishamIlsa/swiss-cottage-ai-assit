import concurrent.futures
import re
from pathlib import Path
from typing import Any

from entities.document import Document
from helpers.log import get_logger
from tqdm import tqdm
from unstructured.partition.auto import partition

logger = get_logger(__name__)

# Try to import yaml for frontmatter parsing
try:
    import yaml
    YAML_SUPPORT = True
except ImportError:
    YAML_SUPPORT = False
    logger.warning("yaml not available - frontmatter parsing disabled. Install with: pip install pyyaml")


class DirectoryLoader:
    """Load documents from a directory."""

    def __init__(
        self,
        path: Path,
        glob: str = "**/[!.]*",
        recursive: bool = False,
        show_progress: bool = False,
        use_multithreading: bool = False,
        max_concurrency: int = 4,
        **partition_kwargs: Any,
    ):
        """Initialize with a path to directory and how to glob over it.

        Args:
            path: Path to directory.
            glob: Glob pattern to use to find files. Defaults to "**/[!.]*"
               (all files except hidden).
            recursive: Whether to recursively search for files. Defaults to False.
            show_progress: Whether to show a progress bar. Defaults to False.
            use_multithreading: Whether to use multithreading. Defaults to False.
            max_concurrency: The maximum number of threads to use. Defaults to 4.
            partition_kwargs: Keyword arguments to pass to unstructured `partition` function.
        """
        self.path = path
        self.glob = glob
        self.recursive = recursive
        self.show_progress = show_progress
        self.use_multithreading = use_multithreading
        self.max_concurrency = max_concurrency
        self.partition_kwargs = partition_kwargs

    def load(self) -> list[Document]:
        """Load documents."""
        if not self.path.exists():
            raise FileNotFoundError(f"Directory not found: '{self.path}'")
        if not self.path.is_dir():
            raise ValueError(f"Expected directory, got file: '{self.path}'")

        docs: list[Document] = []
        items = list(self.path.rglob(self.glob) if self.recursive else self.path.glob(self.glob))

        pbar = None
        if self.show_progress:
            pbar = tqdm(total=len(items))

        if self.use_multithreading:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_concurrency) as executor:
                executor.map(lambda item: self.load_file(item, docs, pbar), items)
        else:
            for i in items:
                self.load_file(i, docs, pbar)

        if pbar:
            pbar.close()

        return docs

    def load_file(self, doc_path: Path, docs: list[Document], pbar: Any | None) -> None:
        """
        Load document from the specified path.

        Args:
            doc_path (str): The path to the document.
            docs: List of documents to append to.
            pbar: Progress bar. Defaults to None.

        """
        if doc_path.is_file():
            try:
                logger.debug(f"Processing file: {str(doc_path)}")
                # For markdown files, read directly to avoid unstructured issues
                if doc_path.suffix.lower() == '.md':
                    text = doc_path.read_text(encoding='utf-8')
                    
                    # Parse YAML frontmatter if present
                    metadata = {"source": str(doc_path)}
                    frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
                    match = re.match(frontmatter_pattern, text, re.DOTALL)
                    
                    if match and YAML_SUPPORT:
                        frontmatter_text = match.group(1)
                        content_text = match.group(2)
                        try:
                            frontmatter = yaml.safe_load(frontmatter_text) or {}
                            # Extract metadata from frontmatter - only include non-None values
                            if frontmatter.get("intent"):
                                metadata["intent"] = frontmatter.get("intent")
                            if frontmatter.get("cottage_id") is not None:
                                metadata["cottage_id"] = str(frontmatter.get("cottage_id"))  # Convert to string for ChromaDB
                            if frontmatter.get("category"):
                                metadata["category"] = frontmatter.get("category")
                            if frontmatter.get("faq_id"):
                                metadata["faq_id"] = frontmatter.get("faq_id")
                            if frontmatter.get("type"):
                                metadata["type"] = frontmatter.get("type", "document")
                            # Use content without frontmatter
                            text = content_text
                        except Exception as e:
                            logger.warning(f"Failed to parse frontmatter for {doc_path}: {e}")
                    
                    # Clean metadata - remove None values before creating Document
                    metadata = {k: v for k, v in metadata.items() if v is not None}
                    
                    docs.extend([Document(page_content=text, metadata=metadata)])
                else:
                    # For other file types, use unstructured
                    elements = partition(filename=str(doc_path), **self.partition_kwargs)
                    text = "\n\n".join([str(el) for el in elements])
                    docs.extend([Document(page_content=text, metadata={"source": str(doc_path)})])
            except Exception as e:
                logger.warning(f"Failed to process file {doc_path}: {e}. Skipping...")
            finally:
                if pbar:
                    pbar.update(1)


if __name__ == "__main__":
    root_folder = Path(__file__).resolve().parent.parent.parent
    docs_path = root_folder / "docs"
    loader = DirectoryLoader(
        path=docs_path,
        glob="*.md",
        recursive=True,
        use_multithreading=True,
        show_progress=True,
    )
    documents = loader.load()
    print(f"Loaded {len(documents)} documents.")
