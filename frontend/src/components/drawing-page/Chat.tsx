import { GoDependabot } from 'react-icons/go';
import Input from '../../UI/Input';
import {
    useEffect,
    useRef,
    useState,
    type ChangeEventHandler,
    type SubmitEventHandler,
} from 'react';
import Button from '../../UI/Button';
import MessagesContainer from './MessagesContainer';
import {
    useAskQuestionMutation,
    useLazyGetAskStatusQuery,
} from '../../store/api/drawings';
import { useParams } from 'react-router';

const Chat = () => {
    const [question, setQuestion] = useState<string>('');
    const [isThinking, setIsThinking] = useState<boolean>(false);
    const pollRef = useRef<number | null>(null);
    const params = useParams<{ id: string }>();

    const [messages, setMessages] = useState<
        { type: 'answer' | 'question'; body: string }[]
    >([]);
    const [askQuestion] = useAskQuestionMutation();
    const [triggerStatusCheck] = useLazyGetAskStatusQuery();

    const handleChange: ChangeEventHandler<HTMLInputElement> = (e) => {
        setQuestion(e.target.value);
    };

    const askHandler: SubmitEventHandler<HTMLFormElement> = async (e) => {
        e.preventDefault();
        if (!question.trim()) return;

        const currentQuestion = question;
        setMessages((prev) => [
            ...prev,
            { type: 'question', body: currentQuestion },
        ]);
        setQuestion('');
        setIsThinking(true);

        try {
            await askQuestion({
                id: params.id!,
                question: currentQuestion,
            }).unwrap();

            pollRef.current = setInterval(async () => {
                try {
                    const result = await triggerStatusCheck({
                        id: params.id!,
                    }).unwrap();

                    if (result.status === 'completed') {
                        setMessages((prev) => [
                            ...prev,
                            { type: 'answer', body: result.answer },
                        ]);
                        setIsThinking(false);
                        if (pollRef.current) {
                            clearInterval(pollRef.current);
                            pollRef.current = null;
                        }
                    }
                } catch (err) {
                    console.error('Ошибка при проверке статуса', err);
                }
            }, 3000);
        } catch (error) {
            console.error('Ошибка отправки:', error);
            setMessages((prev) => [
                ...prev,
                { type: 'answer', body: 'Возникла ошибка' },
            ]);
            setIsThinking(false);
        }
    };
    useEffect(() => {
        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
        };
    }, []);
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
