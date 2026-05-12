/* eslint-disable react-hooks/set-state-in-effect */
import { GoDependabot } from 'react-icons/go';
import Input from '../../UI/Input';
import {
    useEffect,
    useState,
    type ChangeEventHandler,
    type FC,
    type SubmitEventHandler,
} from 'react';
import Button from '../../UI/Button';
import MessagesContainer from './MessagesContainer';
import type { IMessage } from '../../types/api';

interface IChat {
    question: string;
    setQuestion: React.Dispatch<React.SetStateAction<string>>;
    isThinking: boolean;
    oldMessages?: IMessage[];
    askHandler: SubmitEventHandler<HTMLFormElement>;
}

const Chat: FC<IChat> = ({
    oldMessages,
    askHandler,
    isThinking,
    question,
    setQuestion,
}) => {
    const [messages, setMessages] = useState<
        { type: 'answer' | 'question'; body: string }[]
    >([]);

    const handleChange: ChangeEventHandler<HTMLInputElement> = (e) => {
        setQuestion(e.target.value);
    };

    useEffect(() => {
        if (oldMessages) {
            const parsedOldMessages = oldMessages.map((mes) => {
                if (mes.role === 'assistant' && mes.content)
                    return { type: 'answer', body: mes.content };
                if (mes.role === 'user' && mes.content)
                    return { type: 'question', body: mes.content };
            });
            if (parsedOldMessages)
                setMessages(
                    parsedOldMessages as {
                        type: 'answer' | 'question';
                        body: string;
                    }[],
                );
        }
    }, [oldMessages]);

    return (
        <div className="w-full h-full flex flex-col border-l-2 border-blue-300">
            <div className="flex h-fit bg-blue-300  items-center gap-4 pl-4 pt-2 pb-2">
                <GoDependabot className="text-3xl" />
                <p className="text-2xl">Чат с AI-ассистентом</p>
            </div>
            <MessagesContainer messages={messages} isLoading={isThinking} />
            <form
                className="flex h-max bg-blue-300 items-center p-2 gap-2"
                onSubmit={askHandler}
            >
                <Input
                    value={question}
                    placeholder="Введите вопрос..."
                    className="w-8/10 bg-blue-100 h-fit rounded-lg"
                    onChange={handleChange}
                    disabled={isThinking}
                />
                <Button
                    disabled={!question || isThinking}
                    type="submit"
                    content="Спросить"
                    className="w-2/10 bg-blue-100 disabled:cursor-not-allowed"
                />
            </form>
        </div>
    );
};

export default Chat;
