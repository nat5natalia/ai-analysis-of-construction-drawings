import { type FC } from 'react';
import img from '../../images/no image.jfif';
import { formatDate } from '../../utils/formatDate';
import { useNavigate } from 'react-router';

interface IDrawing {
    drawing: {
        id: string;
        filename: string;
        uploaded_at?: string;
    };
}

const Drawing: FC<IDrawing> = ({ drawing }) => {
    const navigate = useNavigate();
    return (
        <div
            onClick={() => navigate(`/feed/${drawing.id}`)}
            className="bg-white w-full h-full rounded-2xl cursor-pointer overflow-hidden flex flex-col 
                transition-all duration-300 ease-in-out 
                hover:scale-105 hover:bg-gray-100"
        >
            <div className="flex-1 flex items-center justify-center overflow-hidden p-2">
                <img
                    src={img}
                    alt="drawing"
                    className="object-contain w-full h-full rounded-xl"
                />
            </div>

            {drawing.uploaded_at ? (
                <div className="w-full pl-4 pr-4 pb-2 flex justify-between">
                    <p className="text-gray-600 font-medium truncate">
                        {drawing.filename}
                    </p>
                    <p className="text-gray-400">
                        {formatDate(drawing.uploaded_at)}
                    </p>
                </div>
            ) : (
                <div className="w-full p-2 text-center">
                    <p className="text-gray-600 font-medium truncate">
                        {drawing.filename}
                    </p>
                </div>
            )}
        </div>
    );
};

export default Drawing;
