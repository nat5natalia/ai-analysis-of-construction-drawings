import { TbFaceIdError } from 'react-icons/tb';

const ErrorState = () => {
    return (
        <div className="flex-1 flex justify-center items-center">
            <div className="flex flex-col items-center">
                <TbFaceIdError className="h-40 w-40" />
                <div className="text-2xl text-center">
                    Извините, возникла{' '}
                    <span className="font-medium">непредвиденная ошибка</span>
                </div>
            </div>
        </div>
    );
};

export default ErrorState;
