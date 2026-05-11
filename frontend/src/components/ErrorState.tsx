import { TbFaceIdError } from 'react-icons/tb';

const ErrorState = () => {
    return (
        <div className="flex-1 flex justify-center items-center">
            <div className="flex flex-col items-center">
                <TbFaceIdError className="h-30 w-30 lg:h-40 lg:w-40" />
                <div className="text-xl lg:text-2xl text-center">
                    Извините, возникла{' '}
                    <span className="font-medium">непредвиденная ошибка</span>
                </div>
            </div>
        </div>
    );
};

export default ErrorState;
