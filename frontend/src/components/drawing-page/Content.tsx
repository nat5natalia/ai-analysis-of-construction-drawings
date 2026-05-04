import { useParams } from 'react-router';
import { useGetDrawingQuery } from '../../store/api/drawings';
import image from '../../images/no image.jfif';
import ErrorState from '../ErrorState';
import LoadingState from '../LoadingState';
import { formatDate } from '../../utils/formatDate';

const Content = () => {
    const params = useParams<{ id: string }>();
    const { data, isError, isLoading } = useGetDrawingQuery({ id: params.id! });
    return (
        <>
            <div className="flex mt-6">
                <img className="w-3/5" src={image} alt={image} />
                <div className="w-2/5 flex justify-center h-fit">
                    {isError && (
                        <div className="h-full">
                            <ErrorState />
                        </div>
                    )}
                    {isLoading && <LoadingState />}
                    {data && (
                        <div className="grid grid-cols-2 gap-y-2 mt-10">
                            <div className="text-gray-500">Создано:</div>
                            <div className="text-black">
                                {formatDate(data.uploaded_at)}
                            </div>

                            <div className="text-gray-500">Название файла:</div>
                            <div className="text-black overflow-y-auto">
                                {data.filename}
                            </div>

                            <div className="text-gray-500">Статус:</div>
                            <div className="text-black">{data.status}</div>
                        </div>
                    )}
                </div>
            </div>
            {data && data.description && (
                <p>
                    <span className="text-gray-500">Описание:{'   '}</span>
                    {data.description}
                </p>
            )}
        </>
    );
};

export default Content;
