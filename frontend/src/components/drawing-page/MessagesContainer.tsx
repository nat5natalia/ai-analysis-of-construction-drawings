import { type FC } from 'react';

interface IMessagesContainer {
    messages: { type: 'answer' | 'question'; body: string }[];
    isLoading: boolean;
}

const MessagesContainer: FC<IMessagesContainer> = ({ messages, isLoading }) => {
    return (
        <div className="flex-1 bg-blue-100 overflow-y-auto p-4 flex flex-col gap-3">
            {messages.map((msg, index) => {
                const isQuestion = msg.type === 'question';

                return (
                    <div
                        key={index}
                        className={`flex ${isQuestion ? 'justify-end' : 'justify-start'}`}
                    >
                        <div
                            className={`
                                px-4 py-2 rounded-2xl max-w-[70%] wrap-break-words
                                ${
                                    isQuestion
                                        ? 'bg-white text-black'
                                        : 'bg-blue-200 text-black'
                                }
                            `}
                        >
                            {msg.body}
                        </div>
                    </div>
                );
            })}
            {isLoading && <p>Ассистент думает...</p>}
        </div>
    );
};

export default MessagesContainer;
