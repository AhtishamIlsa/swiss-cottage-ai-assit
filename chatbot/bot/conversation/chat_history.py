class ChatHistory(list):
    def __init__(self, messages: list | None = None, total_length: int = -1):
        """Initialise the queue with a fixed total length.

        Args:
            messages (list | None): A list of initial messages
            total_length (int): The maximum number of messages the chat history can hold.
        """
        if messages is None:
            messages = []

        super().__init__(messages)
        self.total_length = total_length

    def append(self, msg: str):
        """
        Append a message that contains a question and an answer to the chat history.

        Args:
            msg (str): The message to be added to the chat history.
        """
        if len(self) == self.total_length:
            self.pop(0)
        super().append(msg)

    def __str__(self):
        """
        Get the chat history as a single string.

        Returns:
            str: The chat history concatenated into a single string, with each message separated by a newline.
        """
        chat_history = "\n".join([msg for msg in self])
        return chat_history
    
    def get_last_message(self) -> str | None:
        """
        Get the last message from chat history.
        
        Returns:
            Last message string or None if history is empty
        """
        return self[-1] if len(self) > 0 else None