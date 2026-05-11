import { IoArrowBackSharp, IoChatbubbleEllipses } from 'react-icons/io5';

import Button from '../../UI/Button';
import { useNavigate, useParams } from 'react-router';
import Content from './Content';
import { MdDelete } from 'react-icons/md';
import { useDeleteDrawingMutation } from '../../store/api/drawings';
import { toast, ToastContainer } from 'react-toastify';
import Chat from './Chat';
import { useState } from 'react';

const DrawingPage = () => {
    const navigate = useNavigate();
    const params = useParams<{ id: string }>();
    const [deleteDrawing, { isLoading }] = useDeleteDrawingMutation();
    const [isChatOpen, setIsChatOpen] = useState(false);
    const handleDelete = async () => {
        try {
            const result = await deleteDrawing({ id: params.id! }).unwrap();
            console.log(result.message);
            navigate('/feed');
        } catch (err) {
            console.error(err);
            toast.error('Удаление не удалось');
        }
    };
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
                    <Content />
                </div>
            </div>
            <div className="hidden lg:block lg:w-[30%] bg-gray-200">
                <Chat />
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
                    <Chat />

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
