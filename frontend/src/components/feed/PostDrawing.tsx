import { useDropzone } from 'react-dropzone';
import { FaFileUpload } from 'react-icons/fa';
import { useUploadDrawingMutation } from '../../store/api/drawings';
import { toast, ToastContainer } from 'react-toastify';
import { RiLoader4Line } from 'react-icons/ri';

const PostDrawing = () => {
    const [uploadDrawing, { isLoading }] = useUploadDrawingMutation();

    const onDrop = async (acceptedFile: File[]) => {
        const formData = new FormData();
        formData.append('file', acceptedFile[0]);

        try {
            await uploadDrawing({ data: formData }).unwrap();
            toast.success('Файл успешно загружен!');
        } catch (err) {
            console.error(err);
            toast.error('Ошибка загрузки файла');
        }
    };

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        accept: {
            'application/pdf': [],
            'image/png': [],
            'image/jpeg': [],
            'image/tiff': [],
        },
        multiple: false,
    });

    return (
        <div className="flex w-full lg:w-1/5 md:w-1/5 flex-col bg-blue-100 border-2 border-blue-200 pt-5 pb-10 h-fit mt-6 rounded-2xl">
            <p className="ml-2 text-gray-600">• Перетащите чертеж</p>
            <p className="ml-2 text-gray-600">• Или нажмите для выбора</p>
            <div className="w-full flex justify-center mt-4">
                <div
                    {...getRootProps()}
                    className={`relative flex w-2/3 p-5 justify-center items-center rounded-xl cursor-pointer transition-all duration-300
          ${isDragActive ? 'bg-blue-400 scale-105' : 'bg-blue-200 hover:bg-blue-400'}
        `}
                >
                    <input {...getInputProps()} />
                    {isLoading ? (
                        <RiLoader4Line className="text-8xl text-blue-600 transition-all duration-300 " />
                    ) : (
                        <FaFileUpload
                            className={`text-8xl text-blue-600 transition-all duration-300
            ${isDragActive ? 'opacity-30' : 'opacity-100'}
          `}
                        />
                    )}
                    <span
                        className={`absolute text-blue-700 text-center transition-all duration-300
            ${isDragActive ? 'opacity-100' : 'opacity-0'}
          `}
                    >
                        Перетащите чертёж
                    </span>
                </div>
            </div>
            <ToastContainer />
        </div>
    );
};

export default PostDrawing;
