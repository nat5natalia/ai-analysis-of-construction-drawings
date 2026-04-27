import { IoArrowBackSharp } from 'react-icons/io5';

import Button from '../../UI/Button';
import { useNavigate, useParams } from 'react-router';
import Content from './Content';
import { MdDelete } from 'react-icons/md';
import { useDeleteDrawingMutation } from '../../store/api/drawings';
import { toast, ToastContainer } from 'react-toastify';
import Chat from './Chat';

const DrawingPage = () => {
    const navigate = useNavigate();
    const params = useParams<{ id: string }>();
    const [deleteDrawing, { isLoading }] = useDeleteDrawingMutation();
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
        <div className="w-full h-screen flex">
            <div className="w-7/10 bg-gray-100">
                <div className="p-6">
                    <div className="flex gap-2">
                        <Button
                            onClick={() => navigate('/feed')}
                            className="bg-gray-400 hover:bg-gray-500"
                            content="Назад"
                            decoration={<IoArrowBackSharp />}
                        />
                        <Button
                            onClick={handleDelete}
                            className="bg-red-500 hover:bg-red-600"
                            content={!isLoading ? 'Удалить' : 'Загрузка...'}
                            decoration={!isLoading ? <MdDelete /> : <></>}
                        />
                    </div>
                    <Content />
                </div>
            </div>
            <div className="w-3/10 bg-gray-200">
                <Chat />
            </div>
            <ToastContainer />
        </div>
    );
};

export default DrawingPage;
