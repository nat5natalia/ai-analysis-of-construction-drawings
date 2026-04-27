import { GoDependabot } from 'react-icons/go';
import Input from '../../UI/Input';
import {
    useState,
    type ChangeEventHandler,
    type SubmitEventHandler,
} from 'react';
import Button from '../../UI/Button';
import MessagesContainer from './MessagesContainer';
import { useAskQuestionMutation } from '../../store/api/drawings';
import { useParams } from 'react-router';

const Chat = () => {
    const [question, setQuestion] = useState<string>('');
    const params = useParams<{ id: string }>();
    const handleChange: ChangeEventHandler<HTMLInputElement> = (e) => {
        setQuestion(e.target.value);
    };
    const [messages, setMessages] = useState<
        { type: 'answer' | 'question'; body: string }[]
    >([]);
    const [askQuestion, { isLoading }] = useAskQuestionMutation();
    const askHandler: SubmitEventHandler<HTMLFormElement> = async (e) => {
        e.preventDefault();
        setMessages((prev) => [...prev, { type: 'question', body: question }]);
        setQuestion('');
        try {
            const response = await askQuestion({
                id: params.id!,
                question: question,
            });
            if (response.data)
                setMessages((prev) => [
                    ...prev,
                    { type: 'answer', body: response.data.answer },
                ]);
            else
                setMessages((prev) => [
                    ...prev,
                    { type: 'answer', body: 'Произошла ошибка' },
                ]);
        } catch {
            setMessages((prev) => [
                ...prev,
                { type: 'answer', body: 'Произошла ошибка' },
            ]);
        }
    };
    return (
        <div className="w-full h-full flex flex-col">
            <div className="flex h-fit bg-blue-300  items-center gap-4 pl-4 pt-2 pb-2">
                <GoDependabot className="text-3xl" />
                <p className="text-2xl">Чат с AI-ассистентом</p>
            </div>
            <MessagesContainer messages={messages} isLoading={isLoading} />
            <form
                className="flex h-max bg-blue-300 items-center p-2 gap-2"
                onSubmit={askHandler}
            >
                <Input
                    value={question}
                    placeholder="Введите вопрос..."
                    className="w-8/10 bg-blue-100 h-fit rounded-lg"
                    onChange={handleChange}
                />
                <Button
                    disabled={!question ? true : false}
                    type="submit"
                    content="Спросить"
                    className="w-2/10 bg-blue-100 disabled:cursor-not-allowed"
                />
            </form>
        </div>
    );
};

export default Chat;
