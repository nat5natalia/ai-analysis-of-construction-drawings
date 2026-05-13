/* eslint-disable react-hooks/set-state-in-effect */
import { IoArrowBackSharp, IoChatbubbleEllipses } from 'react-icons/io5';
import Button from '../../UI/Button';
import { useNavigate, useParams } from 'react-router';
import Content from './Content';
import { MdDelete } from 'react-icons/md';
import {
    useAskQuestionMutation,
    useGetDrawingQuery,
    useLazyGetDrawingQuery,
} from '../../store/api/drawings';
import { toast, ToastContainer } from 'react-toastify';
import Chat from './Chat';
import { useEffect, useState, type SubmitEventHandler } from 'react';
import { useDeleteDrawing } from '../../hooks/useDeleteDrawing';

const DrawingPage = () => {
    const navigate = useNavigate();
    const params = useParams<{ id: string }>();
    const { isLoading, handleDelete } = useDeleteDrawing(params.id!, navigate);
    const { data, isError } = useGetDrawingQuery(
        {
            id: params.id!,
        },
        { refetchOnMountOrArgChange: true },
    );
    const [triggerGetDrawing] = useLazyGetDrawingQuery();

    const [askQuestion] = useAskQuestionMutation();
    const [question, setQuestion] = useState<string>('');
    console.log(data);

    const askHandler: SubmitEventHandler<HTMLFormElement> = async (e) => {
        e.preventDefault();
        try {
            await askQuestion({
                id: params.id!,
                question,
            }).unwrap();
            await triggerGetDrawing({ id: params.id! }).unwrap();
        } catch (error) {
            console.log(error);
        } finally {
            setQuestion('');
        }
    };

    useEffect(() => {
        if (!params.id) return;

        const ws = new WebSocket(`ws://localhost:8000/ws/${params.id}`);

        ws.onopen = () => {
            console.log('WS connected');
        };

        ws.onerror = (e) => {
            console.log('WS error', e);
        };

        ws.onclose = () => {
            console.log('WS closed');
        };

        ws.onmessage = async (event) => {
            const data = JSON.parse(event.data);

            if (data.status === 'completed') {
                await triggerGetDrawing({
                    id: params.id!,
                });
            }

            if (data.status === 'failed') {
                toast.error('Возникла ошибка обработки чертежа');
                await triggerGetDrawing({
                    id: params.id!,
                });
            }
        };

        return () => ws.close();
    }, [params.id]);

    const [isChatOpen, setIsChatOpen] = useState(false);
    return (
        <div className="w-full h-screen flex flex-col lg:flex-row relative">
            <div className="w-full lg:h-screen lg:w-7/10 bg-blue-50 flex flex-col lg:overflow-hidden">
                <div className="p-4 sm:p-6 flex flex-col flex-1 min-h-0">
                    <div className="flex gap-2">
                        <Button
                            onClick={() => navigate('/feed')}
                            className="bg-blue-200 hover:bg-gray-500 text-sm lg:text-md"
                            content="Назад"
                            decoration={<IoArrowBackSharp />}
                        />
                        <Button
                            onClick={handleDelete}
                            className="bg-red-400 hover:bg-red-500 text-sm lg:text-md"
                            content={!isLoading ? 'Удалить' : 'Загрузка...'}
                            decoration={!isLoading ? <MdDelete /> : <></>}
                        />
                        <button
                            onClick={() => setIsChatOpen(true)}
                            className="lg:hidden ml-auto bg-blue-300 p-2 rounded-lg"
                        >
                            <IoChatbubbleEllipses className="text-2xl" />
                        </button>
                    </div>
                    <Content data={data} isError={isError} />
                </div>
            </div>
            <div className="hidden lg:block lg:w-[30%] bg-gray-200">
                <Chat
                    question={question}
                    setQuestion={setQuestion}
                    isThinking={
                        data
                            ? data.status === 'processing'
                                ? true
                                : false
                            : true
                    }
                    askHandler={askHandler}
                    oldMessages={data?.messages}
                />
            </div>
            <div className="fixed inset-0 z-50 flex lg:hidden pointer-events-none">
                <div
                    className={`absolute inset-0 bg-black/40 transition-opacity duration-300 ${
                        isChatOpen
                            ? 'opacity-100 pointer-events-auto'
                            : 'opacity-0'
                    }`}
                    onClick={() => setIsChatOpen(false)}
                />
                <div
                    className={`
            relative ml-auto w-full sm:w-100 h-full bg-gray-200 shadow-xl
            transform transition-transform duration-300 ease-in-out
            pointer-events-auto
            ${isChatOpen ? 'translate-x-0' : 'translate-x-full'}
        `}
                >
                    <Chat
                        question={question}
                        setQuestion={setQuestion}
                        isThinking={
                            data
                                ? data.status === 'processing'
                                    ? true
                                    : false
                                : true
                        }
                        askHandler={askHandler}
                        oldMessages={data?.messages}
                    />

                    <button
                        onClick={() => setIsChatOpen(false)}
                        className="absolute top-2 right-2 bg-white px-3 py-1 rounded"
                    >
                        ✕
                    </button>
                </div>
            </div>
            <ToastContainer />
        </div>
    );
};

export default DrawingPage;
