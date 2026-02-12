import logging
import uuid
from typing import Any, Callable, Iterable

import chromadb
import chromadb.config
from bot.memory.embedder import Embedder
from bot.memory.vector_database.distance_metric import DistanceMetric, get_relevance_score_fn
from chromadb.utils.batch_utils import create_batches
from cleantext import clean
from entities.document import Document

logger = logging.getLogger(__name__)


class Chroma:
    def __init__(
        self,
        client: chromadb.Client = None,
        embedding: Embedder | None = None,
        persist_directory: str | None = None,
        collection_name: str = "default",
        collection_metadata: dict | None = None,
        is_persistent: bool = True,
    ) -> None:
        if client is not None:
            self.client = client
        else:
            if persist_directory:
                # Store persist_directory for later use
                self._persist_directory = persist_directory
                # Use PersistentClient for persistent storage
                try:
                    self.client = chromadb.PersistentClient(path=persist_directory)
                except Exception as client_err:
                    error_msg = str(client_err).lower()
                    # If schema error during client init, try to delete corrupted DB and recreate
                    if "no such column" in error_msg or "topic" in error_msg or "operationalerror" in error_msg:
                        logger.warning(f"ChromaDB schema error during client initialization: {client_err}")
                        logger.info("Attempting to fix by removing corrupted database...")
                        import os
                        import shutil
                        db_file = Path(persist_directory) / "chroma.sqlite3"
                        if db_file.exists():
                            try:
                                os.remove(db_file)
                                logger.info("Removed corrupted SQLite database")
                            except Exception:
                                pass
                        # Try again
                        self.client = chromadb.PersistentClient(path=persist_directory)
                    else:
                        raise
            else:
                # Use regular Client for in-memory storage
                client_settings = chromadb.config.Settings(is_persistent=is_persistent)
                self.client = chromadb.Client(client_settings)

        self.embedding = embedding

        # Try to get existing collection first, create if it doesn't exist
        # Handle ChromaDB schema errors (e.g., missing 'topic' column)
        # Strategy: Try to get collection directly first (avoids schema issues with list_collections)
        
        collection_loaded = False
        
        # First, try to get the collection directly (this works even if list_collections fails)
        try:
            self.collection = self.client.get_collection(name=collection_name)
            doc_count = self.collection.count()
            
            # Verify collection actually has data by trying to get a sample
            has_data = False
            try:
                sample = self.collection.get(limit=1)
                has_data = sample.get('ids') and len(sample['ids']) > 0
            except Exception as sample_err:
                # If get() fails, try query as fallback
                try:
                    query_result = self.collection.query(query_texts=["test"], n_results=1)
                    has_data = query_result.get('ids') and len(query_result['ids']) > 0 and len(query_result['ids'][0]) > 0
                except Exception:
                    has_data = False
            
            if doc_count > 0:
                logger.info(f"✅ Successfully loaded collection '{collection_name}' with {doc_count} documents")
                collection_loaded = True
            elif has_data:
                # Collection has data but count() returned 0 - use get() to determine actual count
                try:
                    all_ids = self.collection.get()['ids']
                    actual_count = len(all_ids) if all_ids else 0
                    logger.info(f"✅ Successfully loaded collection '{collection_name}' with {actual_count} documents (count() returned 0 but data exists)")
                    collection_loaded = True
                except Exception:
                    logger.warning(f"Collection '{collection_name}' has data but cannot determine count")
                    collection_loaded = True
            else:
                # Collection exists but is truly empty
                logger.warning(f"Collection '{collection_name}' exists but is empty (0 documents)")
                # Check if we should keep it or if there's another collection with data
                try:
                    # Try to list all collections to see if there's one with data
                    all_collections = self.client.list_collections()
                    for col in all_collections:
                        if col.name != collection_name:
                            col_count = col.count()
                            if col_count > 0:
                                logger.warning(f"Found another collection '{col.name}' with {col_count} documents, but using requested '{collection_name}'")
                except Exception:
                    pass
                # Keep the empty collection - it might be newly created and waiting for data
                logger.info(f"Keeping empty collection '{collection_name}' - it may be populated later")
                collection_loaded = True  # Accept empty collection
        except Exception as get_err:
            error_msg = str(get_err).lower()
            # If it's a "not found" error, collection doesn't exist - we'll create it
            if "not found" in error_msg or "does not exist" in error_msg:
                logger.info(f"Collection '{collection_name}' not found, will create new collection")
                collection_loaded = False
            # If it's a schema error, try to work around it
            # The collection might exist but ChromaDB metadata queries fail
            # Strategy: get_collection() often works even when list_collections() fails
            elif "no such column" in error_msg or "topic" in error_msg or "operationalerror" in error_msg:
                logger.warning(f"Schema error when getting collection via normal path: {get_err}")
                logger.info("Attempting workaround: accessing collection directly (bypassing metadata queries)...")
                
                # The error occurred when trying to get collection via self.client.get_collection()
                # But sometimes we can still access it directly even with schema errors
                # Try using the existing client but catch the specific error
                try:
                    # Try to get collection directly using the existing client
                    # This might work even if the initial attempt failed
                    raw_collection = self.client.get_collection(name=collection_name)
                    raw_count = raw_collection.count()
                    
                    if raw_count > 0:
                        # Success! Collection exists and has data
                        self.collection = raw_collection
                        logger.info(f"✅ Successfully loaded collection '{collection_name}' with {raw_count} documents (workaround succeeded)")
                        collection_loaded = True
                    else:
                        # Collection exists but is empty
                        logger.warning(f"Collection '{collection_name}' exists but is empty (0 documents)")
                        self.collection = raw_collection
                        collection_loaded = True
                        
                except Exception as workaround_err:
                    workaround_msg = str(workaround_err).lower()
                    # If workaround also fails with schema error, try one more time with fresh client
                    if "no such column" in workaround_msg or "topic" in workaround_msg or "operationalerror" in workaround_msg:
                        logger.warning(f"First workaround also hit schema error: {workaround_err}")
                        logger.info("Trying one more time with a fresh client instance...")
                        try:
                            # Create a completely fresh client
                            fresh_client = chromadb.PersistentClient(path=persist_directory if persist_directory else ".")
                            fresh_collection = fresh_client.get_collection(name=collection_name)
                            fresh_count = fresh_collection.count()
                            
                            if fresh_count > 0:
                                # Success with fresh client!
                                self.collection = fresh_collection
                                self.client = fresh_client  # Update client reference
                                logger.info(f"✅ Successfully loaded collection '{collection_name}' with {fresh_count} documents (fresh client workaround succeeded)")
                                collection_loaded = True
                            else:
                                # Collection exists but is empty
                                logger.warning(f"Collection '{collection_name}' exists but is empty")
                                self.collection = fresh_collection
                                self.client = fresh_client
                                collection_loaded = True
                        except Exception as final_err:
                            # Final attempt failed - collection is truly inaccessible
                            logger.error(f"All workaround attempts failed. Final error: {final_err}")
                            logger.error("Collection may exist but cannot be accessed due to schema mismatch.")
                            raise RuntimeError(
                                f"ChromaDB schema error: {get_err}. Please rebuild: "
                                "rm -rf vector_store && python3 excel_faq_extractor.py --excel 'Swiss Cottages FAQS.xlsx'"
                            )
                    else:
                        # Different error type - re-raise
                        raise
            else:
                # Other error, re-raise
                raise
        
        # If collection wasn't loaded, create it (only if it truly doesn't exist)
        if not collection_loaded:
            try:
                self.collection = self.client.create_collection(
                    name=collection_name,
                    embedding_function=None,
                    metadata=collection_metadata,
                )
                logger.info(f"Created new empty collection: {collection_name}")
            except Exception as create_err:
                error_msg = str(create_err).lower()
                # If collection already exists error, try to get it one more time
                if "already exists" in error_msg or "duplicate" in error_msg:
                    logger.info("Collection already exists, trying to get it again...")
                    try:
                        self.collection = self.client.get_collection(name=collection_name)
                        doc_count = self.collection.count()
                        logger.info(f"✅ Successfully loaded existing collection '{collection_name}' with {doc_count} documents")
                    except Exception as final_err:
                        logger.error(f"Failed to get existing collection: {final_err}")
                        raise
                else:
                    raise

    @property
    def embeddings(self) -> Embedder | None:
        return self.embedding

    def __query_collection(
        self,
        query_texts: list[str] | None = None,
        query_embeddings: list[list[float]] | None = None,
        n_results: int = 4,
        where: dict[str, str] | None = None,
        where_document: dict[str, str] | None = None,
        **kwargs: Any,
    ):
        """
        Query the chroma collection.

        Args:
            query_texts: List of query texts.
            query_embeddings: List of query embeddings.
            n_results: Number of results to return. Defaults to 4.
            where: dict used to filter results by
                    e.g. {"color" : "red", "price": 4.20}.
            where_document: dict used to filter by the documents.
                    E.g. {$contains: {"text": "hello"}}.
            kwargs: Additional keyword arguments to pass to Chroma collection query.

        Returns:
            List of `n_results` nearest neighbor embeddings for provided
            query_embeddings or query_texts.

        See more: https://docs.trychroma.com/reference/py-collection#query
        """
        # WORKAROUND: ChromaDB query() and get() have bugs in FastAPI context (works in direct tests)
        # Try to get a fresh collection reference to avoid threading/state issues
        try:
            # Get a fresh collection reference
            fresh_collection = self.client.get_collection(name=self.collection.name)
            # Get all documents from collection
            all_data = fresh_collection.get(limit=None)
            
            if not all_data or "documents" not in all_data:
                logger.error("collection.get() returned no data")
                return {"documents": [[]], "metadatas": [[]], "distances": [[]]}
            
            all_docs = all_data["documents"]
            all_metadatas = all_data.get("metadatas", [])
            all_ids = all_data.get("ids", [])
            
            if not isinstance(all_docs, list) or len(all_docs) == 0:
                logger.error("No documents found in collection")
                return {"documents": [[]], "metadatas": [[]], "distances": [[]]}
            
            # Get query embedding
            query_embedding = None
            if query_embeddings is not None and len(query_embeddings) > 0:
                query_embedding = query_embeddings[0]
            elif query_texts is not None and len(query_texts) > 0 and self.embedding is not None:
                query_embedding = self.embedding.embed_query(query_texts[0])
            
            if query_embedding is None:
                logger.error("Could not generate query embedding")
                return {"documents": [[]], "metadatas": [[]], "distances": [[]]}
            
            # Get stored embeddings for all documents
            stored_embeddings = []
            try:
                # Try to get embeddings from collection - use get() without ids first to avoid issues
                try:
                    embeddings_data = fresh_collection.get(include=["embeddings"])
                    if embeddings_data and "embeddings" in embeddings_data:
                        emb_list = embeddings_data["embeddings"]
                        if isinstance(emb_list, list) and len(emb_list) > 0:
                            stored_embeddings = emb_list
                except Exception as emb_err1:
                    logger.warning(f"Could not retrieve embeddings (method 1): {emb_err1}")
                    # Try with ids if we have them
                    if all_ids and len(all_ids) > 0:
                        try:
                            embeddings_data = fresh_collection.get(ids=all_ids[:100], include=["embeddings"])  # Limit to 100 to avoid issues
                            if embeddings_data and "embeddings" in embeddings_data:
                                emb_list = embeddings_data["embeddings"]
                                if isinstance(emb_list, list) and len(emb_list) > 0:
                                    stored_embeddings = emb_list
                        except Exception as emb_err2:
                            logger.warning(f"Could not retrieve embeddings (method 2): {emb_err2}")
            except Exception as emb_err:
                logger.warning(f"Could not retrieve stored embeddings: {emb_err}")
            
            # If we can't get stored embeddings, we can't compute similarity
            # Just return first N documents
            if not stored_embeddings or len(stored_embeddings) == 0:
                logger.warning("No stored embeddings available, returning first N documents without similarity")
                n = min(n_results, len(all_docs))
                return {
                    "documents": [all_docs[:n]],
                    "metadatas": [all_metadatas[:n] if len(all_metadatas) >= n else all_metadatas + [{}] * (n - len(all_metadatas))],
                    "distances": [[0.5] * n],  # Dummy distances
                }
            
            # Compute cosine similarity for all documents
            import numpy as np
            similarities = []
            for stored_emb in stored_embeddings:
                if stored_emb is None:
                    similarities.append(0.0)
                    continue
                try:
                    # Cosine similarity
                    query_vec = np.array(query_embedding)
                    stored_vec = np.array(stored_emb)
                    dot_product = np.dot(query_vec, stored_vec)
                    norm_query = np.linalg.norm(query_vec)
                    norm_stored = np.linalg.norm(stored_vec)
                    if norm_query > 0 and norm_stored > 0:
                        similarity = dot_product / (norm_query * norm_stored)
                    else:
                        similarity = 0.0
                    # Convert similarity to distance (1 - similarity)
                    distance = 1.0 - similarity
                    similarities.append(distance)
                except Exception as sim_err:
                    logger.warning(f"Error computing similarity: {sim_err}")
                    similarities.append(1.0)  # Max distance if error
            
            # Sort by distance (lower is better) and get top N
            doc_scores = list(zip(all_docs, all_metadatas, similarities))
            doc_scores.sort(key=lambda x: x[2])  # Sort by distance
            top_n = doc_scores[:n_results]
            
            # Format result
            result = {
                "documents": [[doc for doc, _, _ in top_n]],
                "metadatas": [[meta if meta else {} for _, meta, _ in top_n]],
                "distances": [[dist for _, _, dist in top_n]],
            }
            
            logger.info(f"Manual similarity computation succeeded: returning {len(top_n)} documents")
            return result
        except Exception as fallback_err:
            logger.error(f"Manual similarity computation failed: {fallback_err}")
            import traceback
            logger.error(traceback.format_exc())
            # Return empty results as last resort
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    def add_texts(
        self,
        texts: Iterable[str],
        metadatas: list[dict] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]:
        """
        Run more texts through the embeddings and add to the vectorstore.

        Args:
            texts (Iterable[str]): Texts to add to the vectorstore.
            metadatas (list[dict] | None): Optional list of metadatas.
            ids (list[dict] | None): Optional list of IDs.

        Returns:
            List[str]: List of IDs of the added texts.
        """
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]
        embeddings = None
        texts = list(texts)
        if self.embedding is not None:
            embeddings = self.embedding.embed_documents(texts)
        if metadatas:
            # fill metadatas with empty dicts if somebody
            # did not specify metadata for all texts
            length_diff = len(texts) - len(metadatas)
            if length_diff:
                metadatas = metadatas + [{}] * length_diff
            empty_ids = []
            non_empty_ids = []
            for idx, m in enumerate(metadatas):
                if m:
                    non_empty_ids.append(idx)
                else:
                    empty_ids.append(idx)
            if non_empty_ids:
                metadatas = [metadatas[idx] for idx in non_empty_ids]
                texts_with_metadatas = [texts[idx] for idx in non_empty_ids]
                embeddings_with_metadatas = [embeddings[idx] for idx in non_empty_ids] if embeddings else None
                ids_with_metadata = [ids[idx] for idx in non_empty_ids]
                try:
                    self.collection.upsert(
                        metadatas=metadatas,
                        embeddings=embeddings_with_metadatas,
                        documents=texts_with_metadatas,
                        ids=ids_with_metadata,
                    )
                except ValueError as e:
                    if "Expected metadata value to be" in str(e):
                        msg = "Try filtering complex metadata from the document."
                        raise ValueError(e.args[0] + "\n\n" + msg)
                    else:
                        raise e
            if empty_ids:
                texts_without_metadatas = [texts[j] for j in empty_ids]
                embeddings_without_metadatas = [embeddings[j] for j in empty_ids] if embeddings else None
                ids_without_metadatas = [ids[j] for j in empty_ids]
                self.collection.upsert(
                    embeddings=embeddings_without_metadatas,
                    documents=texts_without_metadatas,
                    ids=ids_without_metadatas,
                )
        else:
            self.collection.upsert(
                embeddings=embeddings,
                documents=texts,
                ids=ids,
            )
        return ids

    def from_texts(
        self,
        texts: list[str],
        metadatas: list[dict] | None = None,
        ids: list[str] | None = None,
    ) -> None:
        """
        Adds a batch of texts to the Chroma collection, optionally with metadata and IDs.

        Args:
            texts (list[str]): List of texts to add to the collection.
            metadatas (list[dict], optional): List of metadata dictionaries corresponding to the texts.
                Defaults to None.
            ids (list[str], optional): List of IDs for the texts. If not provided, UUIDs will be generated.
                Defaults to None.

        Returns:
            None
        """
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]

        for batch in create_batches(
            api=self.client,
            ids=ids,
            metadatas=metadatas,
            documents=texts,
        ):
            self.add_texts(
                texts=batch[3] if batch[3] else [],
                metadatas=batch[2] if batch[2] else None,
                ids=batch[0],
            )

    def from_chunks(self, chunks: list) -> None:
        """
        Adds a batch of documents to the Chroma collection.

        Args:
            chunks (list): List of Document objects to add to the collection.
        """
        texts = [clean(doc.page_content) for doc in chunks]
        metadatas = [doc.metadata for doc in chunks]
        self.from_texts(
            texts=texts,
            metadatas=metadatas,
        )

    def similarity_search_with_threshold(
        self,
        query: str,
        k: int = 4,
        threshold: float | None = 0.2,
        filter: dict[str, str] | None = None,
    ) -> tuple[list[Document], list[dict[str, Any]]]:
        """
        Performs similarity search on the given query.

        Parameters:
        -----------
        query : str
            The query string.

        k : int, optional
            The number of retrievals to consider (default is 4).

        threshold : float, optional
            The threshold for considering similarity scores (default is 0.2).

        filter : dict[str, str] | None, optional
            Filter by metadata. Defaults to None.

        Returns:
        -------
        tuple[list[Document], list[dict[str, Any]]]
            A tuple containing the list of matched documents and a list of their sources.

        """
        # Use similarity_search_with_score which supports filter, then convert to relevance scores
        if filter is not None:
            docs_and_scores = self.similarity_search_with_score(query, k, filter=filter)
            # Convert distance scores to relevance scores (lower distance = higher relevance)
            # ChromaDB returns distance scores, so we need to convert them
            # For now, use a simple conversion: relevance = 1 / (1 + distance)
            docs_and_scores = [(doc, 1.0 / (1.0 + score)) for doc, score in docs_and_scores]
        else:
            # `similarity_search_with_relevance_scores` return docs and relevance scores in the range [0, 1].
            # 0 is dissimilar, 1 is most similar.
            docs_and_scores = self.similarity_search_with_relevance_scores(query, k)

        if threshold is not None:
            docs_and_scores = [doc for doc in docs_and_scores if doc[1] > threshold]
            if len(docs_and_scores) == 0:
                logger.warning("No relevant docs were retrieved using the relevance score" f" threshold {threshold}")

            docs_and_scores = sorted(docs_and_scores, key=lambda x: x[1], reverse=True)

        retrieved_contents = [doc[0] for doc in docs_and_scores]
        sources = []
        for doc, score in docs_and_scores:
            sources.append(
                {
                    "score": round(score, 3),
                    "document": doc.metadata.get("source"),
                    "content_preview": f"{doc.page_content[0:256]}...",
                }
            )

        return retrieved_contents, sources

    def similarity_search(self, query: str, k: int = 4, filter: dict[str, str] | None = None) -> list[Document]:
        """
        Run similarity search with Chroma.

        Args:
            query (str): Query text to search for.
            k (int): Number of results to return. Defaults to 4.
            filter (dict[str, str]|None): Filter by metadata. Defaults to None.

        Returns:
            List[Document]: List of documents most similar to the query text.
        """
        docs_and_scores = self.similarity_search_with_score(query, k, filter=filter)
        return [doc for doc, _ in docs_and_scores]

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        filter: dict[str, str] | None = None,
        where_document: dict[str, str] | None = None,
    ) -> list[tuple[Document, float]]:
        """
        Run similarity search with Chroma with distance.

        Args:
            query (str): Query text to search for.
            k (int): Number of results to return. Defaults to 4.
            filter (dict[str, str]|None): Filter by metadata. Defaults to None.
            where_document (dict[str, str]|None): Filter by document content. Defaults to None.
            **kwargs (Any): Additional keyword arguments.

        Returns:
            list[tuple[Document, float]]: List of documents most similar to
            the query text and cosine distance in float for each.
            Lower score represents more similarity.
        """
        try:
            # Always use query_texts (ChromaDB handles embedding internally)
            # This is more reliable and avoids embedding function issues
            # Don't pass where/where_document if None to avoid ChromaDB internal errors
            results = self.__query_collection(
                query_texts=[query],
                n_results=k,
                where=filter if filter is not None else None,
                where_document=where_document if where_document is not None else None,
            )
        except Exception as e:
            logger.error(f"Error in __query_collection: {e}")
            return []
        
        # Handle empty or malformed results
        if not results or not isinstance(results, dict):
            logger.warning(f"Query returned unexpected result type: {type(results)}")
            return []
        
        # Check if results have the expected structure
        if "documents" not in results or not results["documents"]:
            logger.warning("Query returned no documents")
            return []
        
        # Ensure we have lists, not single values
        try:
            documents = results["documents"][0] if isinstance(results["documents"], list) and len(results["documents"]) > 0 else []
            metadatas = results["metadatas"][0] if isinstance(results["metadatas"], list) and len(results["metadatas"]) > 0 else [{}] * len(documents) if documents else []
            distances = results["distances"][0] if isinstance(results["distances"], list) and len(results["distances"]) > 0 else [0.0] * len(documents) if documents else []
            
            # Ensure all lists have the same length
            if not isinstance(documents, list) or not isinstance(metadatas, list) or not isinstance(distances, list):
                logger.error(f"Invalid result types: documents={type(documents)}, metadatas={type(metadatas)}, distances={type(distances)}")
                return []
            
            min_len = min(len(documents), len(metadatas), len(distances))
            if min_len == 0:
                return []
            
            return [
                (Document(page_content=doc, metadata=meta or {}), dist)
                for doc, meta, dist in zip(documents[:min_len], metadatas[:min_len], distances[:min_len])
            ]
        except TypeError as te:
            logger.error(f"TypeError processing query results: {te}, results type: {type(results)}")
            return []
        except Exception as e:
            logger.error(f"Error processing query results: {e}")
            return []

    def __select_relevance_score_fn(self) -> Callable[[float], float]:
        """
        The 'correct' relevance function may differ depending on the distance/similarity metric used by the VectorStore.
        """

        distance = DistanceMetric.L2
        distance_key = "hnsw:space"
        metadata = self.collection.metadata

        if metadata and distance_key in metadata:
            distance = metadata[distance_key]
        return get_relevance_score_fn(distance)

    def similarity_search_with_relevance_scores(self, query: str, k: int = 4) -> list[tuple[Document, float]]:
        """
        Return docs and relevance scores in the range [0, 1].

        0 is dissimilar, 1 is most similar.

        Args:
            query: input text
            k: Number of Documents to return. Defaults to 4.

        Returns:
            List of Tuples of (doc, similarity_score)
        """
        # relevance_score_fn is a function to calculate relevance score from distance.
        relevance_score_fn = self.__select_relevance_score_fn()

        try:
            docs_and_scores = self.similarity_search_with_score(query, k)
            # Validate result is a list
            if not isinstance(docs_and_scores, list):
                logger.error(f"similarity_search_with_score returned non-list: {type(docs_and_scores)}")
                return []
        except Exception as e:
            logger.error(f"Error in similarity_search_with_score: {e}")
            return []
        
        try:
            docs_and_similarities = [(doc, relevance_score_fn(score)) for doc, score in docs_and_scores]
            if any(similarity < 0.0 or similarity > 1.0 for _, similarity in docs_and_similarities):
                logger.warning("Relevance scores must be between" f" 0 and 1, got {docs_and_similarities}")
            return docs_and_similarities
        except Exception as e:
            logger.error(f"Error processing docs_and_scores: {e}")
            return []
