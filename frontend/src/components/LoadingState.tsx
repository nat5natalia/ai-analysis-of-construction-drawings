import { AiOutlineLoading3Quarters } from 'react-icons/ai';

const LoadingState = () => {
    return (
        <div className="flex-1 flex justify-center items-center">
            <div className="flex flex-col items-center">
                <AiOutlineLoading3Quarters className="h-20 w-20 animate-spin" />
                <div className="text-2xl text-center mt-6">
                    <span className="font-medium">Загрузка...</span>
                </div>
            </div>
        </div>
    );
};

export default LoadingState;
