import type { NavigateFunction } from 'react-router';
import { useDeleteDrawingMutation } from '../store/api/drawings';
import { toast } from 'react-toastify';

export const useDeleteDrawing = (id: string, navigate: NavigateFunction) => {
    const [deleteDrawing, { isLoading }] = useDeleteDrawingMutation();
    const handleDelete = async () => {
        try {
            const result = await deleteDrawing({ id }).unwrap();
            console.log(result.message);
            navigate('/feed');
        } catch (err) {
            console.error(err);
            toast.error('Удаление не удалось');
        }
    };
    return { isLoading, handleDelete };
};
