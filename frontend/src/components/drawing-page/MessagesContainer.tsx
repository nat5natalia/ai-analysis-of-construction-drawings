import { type FC } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';

interface IMessagesContainer {
    messages: { type: 'answer' | 'question'; body: string }[];
    isLoading: boolean;
    bottomRef: React.RefObject<HTMLDivElement | null>;
}

const MessagesContainer: FC<IMessagesContainer> = ({
    messages,
    isLoading,
    bottomRef,
}) => {
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
                            {msg.type !== 'answer' ? (
                                msg.body
                            ) : (
                                <ReactMarkdown
                                    remarkPlugins={[remarkGfm]}
                                    rehypePlugins={[rehypeSanitize]}
                                    components={{
                                        table: ({ children }) => (
                                            <div className="overflow-x-auto w-full">
                                                <table className="min-w-max border-collapse">
                                                    {children}
                                                </table>
                                            </div>
                                        ),
                                    }}
                                >
                                    {msg.body}
                                </ReactMarkdown>
                            )}
                        </div>
                    </div>
                );
            })}

            {isLoading && <p>Ассистент думает...</p>}
            <div ref={bottomRef} />
        </div>
    );
};

export default MessagesContainer;
