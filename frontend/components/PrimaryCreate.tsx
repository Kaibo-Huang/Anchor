import React, {useEffect, useState} from 'react'
import Button from '@mui/material/Button';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import {styled} from "@mui/system";
import {IconButton, TextField, Typography, CircularProgress} from "@mui/material";
import SendIcon from '@mui/icons-material/Send';
import { useRouter } from 'next/navigation';
import { createEvent, uploadVideoV2, uploadMusic, analyzeMusic } from '@/lib/api';

const imgVector = "/anchor-wave.svg"
const imgAnchorLogo22 = "/Anchor FInal.svg"
const arrow = "/arrow1.svg"

const VisuallyHiddenInput = styled('input')({
    clip: 'rect(0 0 0 0)',
    clipPath: 'inset(50%)',
    height: 1,
    overflow: 'hidden',
    position: 'absolute',
    bottom: 0,
    left: 0,
    whiteSpace: 'nowrap',
    width: 1,
});

const infoCaptions = [
    <Typography key="caption-0" variant="h2" gutterBottom>Create a Video of Your <br/> Most Important Moments</Typography>,
    <Typography key="caption-1" variant="h2" gutterBottom>Give Some Context</Typography>,
    <Typography key="caption-2" variant="h2" gutterBottom>Add Some Music</Typography>,
    <Typography key="caption-3" variant="h2" gutterBottom>Include crowd reactions</Typography>,
]

const infoContent = [
    <Typography key="content-0" variant="h4">Upload videos from your computer to get <br/> started.</Typography>,
    <Typography key="content-1" variant="h4">Explain what these videos are about. <br/> Talk about what is in them.</Typography>,
    <Typography key="content-2" variant="h4">Pick what kind of energy you want to <br/> express yourself with.</Typography>,
    <Typography key="content-3" variant="h4">Include crowd reactions</Typography>,
]

export default function PrimaryCreate() {
    const router = useRouter();
    const [step, setStep] = React.useState(0);
    const [videoContext, setVideoContext] = React.useState("");

    // State for fade transition
    const [displayedStep, setDisplayedStep] = useState(0);
    const [isFadingOut, setIsFadingOut] = useState(false);

    // State for window dimensions (to avoid SSR issues)
    const [windowSize, setWindowSize] = useState({width: 0, height: 0});

    // State to track when step 3 animation is complete
    const [animationComplete, setAnimationComplete] = useState(false);

    // State for chat input
    const [chatInput, setChatInput] = useState("");

    // State to track when step 4 animation is complete (elements should be removed)
    const [step4AnimationComplete, setStep4AnimationComplete] = useState(false);

    // Backend integration state
    const [videoFiles, setVideoFiles] = useState<File[]>([]);
    const [musicFile, setMusicFile] = useState<File | null>(null);
    const [isProcessing, setIsProcessing] = useState(false);
    const [processingMessage, setProcessingMessage] = useState("");

    // Handle sending the chat message and creating event
    const handleSend = async () => {
        if (chatInput.trim() && videoFiles.length > 0) {
            setStep(4);
            setIsProcessing(true);

            try {
                // Step 1: Create event with the user's description
                setProcessingMessage("Creating your event...");
                const event = await createEvent({
                    name: chatInput.trim(),
                    event_type: 'sports' // Default, could be inferred from description
                });

                console.log("Event created:", event);

                // Step 2: Upload videos
                setProcessingMessage(`Uploading ${videoFiles.length} video${videoFiles.length > 1 ? 's' : ''}...`);
                const videoUploads = videoFiles.map((file, index) =>
                    uploadVideoV2(event.id, file, 'wide', (stage, progress) => {
                        console.log(`Video ${index + 1} ${stage}: ${progress}%`);
                    })
                );

                await Promise.all(videoUploads);
                console.log("All videos uploaded");

                // Step 3: Upload music if provided
                if (musicFile) {
                    setProcessingMessage("Uploading music...");
                    await uploadMusic(event.id, musicFile);
                    console.log("Music uploaded");

                    // Trigger music analysis
                    setProcessingMessage("Analyzing music beats...");
                    await analyzeMusic(event.id);
                    console.log("Music analyzed");
                }

                // Step 4: Navigate to event page
                setProcessingMessage("Taking you to your event...");
                setTimeout(() => {
                    router.push(`/events/${event.id}`);
                }, 500);

            } catch (error) {
                console.error("Error creating event:", error);
                setProcessingMessage("Error: " + (error instanceof Error ? error.message : "Something went wrong"));
                setIsProcessing(false);
            }

            setChatInput("");
        }
    };

    // Handle Enter key to send, Shift+Enter for new line
    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    // Handle window dimensions on client side only
    useEffect(() => {
        const handleResize = () => {
            setWindowSize({width: window.innerWidth, height: window.innerHeight});
        };

        // Set initial size
        handleResize();

        // Add resize listener
        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
    }, []);

    // Handle step 3 animation completion
    useEffect(() => {
        if (step === 3) {
            const timeout = setTimeout(() => {
                setAnimationComplete(true);
            }, 650); // Wait for slide-right + section-fade-out to complete
            return () => clearTimeout(timeout);
        }

        const timeout = setTimeout(() => {
            setAnimationComplete(false);
        }, 0);
        return () => clearTimeout(timeout);
    }, [step]);

    // Handle step 4 animation completion - remove elements after slide up
    useEffect(() => {
        if (step >= 4) {
            const timeout = setTimeout(() => {
                setStep4AnimationComplete(true);
            }, 800); // Match the slide-up-off-screen animation duration
            return () => clearTimeout(timeout);
        }

        const timeout = setTimeout(() => {
            setStep4AnimationComplete(false);
        }, 0);
        return () => clearTimeout(timeout);
    }, [step]);

    // Handle step changes with fade-out-then-fade-in
    useEffect(() => {
        if (step !== displayedStep) {
            const timeout1 = setTimeout(() => {
                setIsFadingOut(true);
            }, 0);
            const timeout2 = setTimeout(() => {
                setDisplayedStep(step);
                setIsFadingOut(false);
            }, 400); // Match fade-out duration
            return () => {
                clearTimeout(timeout1);
                clearTimeout(timeout2);
            };
        }
    }, [step, displayedStep]);

    return (
        <div className="relative" style={{height: "100vh", width: "100vw", overflow: "hidden"}}>
            {/* Anchor Logo - positioned at 3.5vw from left, 7vh from top */}
            <div className="absolute z-20" style={{left: '3vw', top: '5vh', width: '32vw'}}>
                <img src={imgAnchorLogo22} alt="Anchor logo" className="w-full h-auto object-contain"/>
            </div>

            {/* Blue screen background - revealed when content slides away */}
            <div
                className="fixed inset-0 z-0"
                style={{
                    backgroundColor: '#FAFAFA',
                    opacity: step >= 3 ? 1 : 0,
                    transition: 'opacity 0.4s ease-in-out'
                }}
            />

            {/* Processing overlay */}
            {isProcessing && (
                <div
                    className="fixed inset-0 flex flex-col items-center justify-center"
                    style={{
                        zIndex: 100,
                        backgroundColor: 'rgba(64, 120, 242, 0.95)',
                    }}
                >
                    <CircularProgress size={60} sx={{ color: 'white', marginBottom: '2rem' }} />
                    <Typography variant="h3" sx={{ color: 'white', textAlign: 'center' }}>
                        {processingMessage}
                    </Typography>
                </div>
            )}

            {!step4AnimationComplete && <div className={step >= 4 ? 'slide-up-off-screen' : ''}>
                {/* AI Chatbot-style interface that appears after animation completes */}
                {animationComplete && (
                    <div
                        className={`fixed inset-0 flex flex-col items-center justify-center textfield-fade-in`}
                        style={{zIndex: 55}}
                    >
                        <div
                            style={{
                                width: '50vw',
                                maxWidth: '45vw',
                                height: '30vh',
                                padding: '2rem',
                                display: 'flex',
                                flexDirection: 'column',
                            }}>

                            {/* Chat header */}
                            <div style={{marginBottom: '1.5rem', textAlign: 'center', flexShrink: 0}}>
                                <Typography
                                    variant="h1"
                                    sx={{
                                        fontWeight: 600,
                                        marginBottom: '0.5rem'
                                    }}
                                >
                                    What kind of video do<br/> you want?
                                </Typography>
                                <Typography
                                    variant="body1"
                                    sx={{color: '#CFD0D1'}}
                                >
                                    Describe your vision and we&apos;ll help bring it to life
                                </Typography>
                            </div>

                            {/* Spacer to push input to bottom */}
                            <div style={{flex: 1, minHeight: "1vh"}}/>

                            {/* Chat input area - fixed height */}
                            <div
                                className="chat-input-wrapper"
                                style={{
                                    flexShrink: 0,
                                    maxHeight: '50vh',
                                    minHeight: '4vh',
                                }}
                            >
                                <TextField
                                    value={chatInput}
                                    onChange={(e) => setChatInput(e.target.value)}
                                    onKeyDown={handleKeyDown}
                                    placeholder="e.g., 'Find my best moments from the game' or 'Create a highlight reel with high energy'"
                                    multiline
                                    fullWidth
                                    variant="outlined"
                                    disabled={isProcessing}
                                    sx={{
                                        '& .MuiOutlinedInput-root': {
                                            borderRadius: '20px',
                                            backgroundColor: 'transparent',
                                            maxHeight: '10vh    ',
                                            overflow: 'auto',
                                            '& fieldset': {
                                                border: 'none',
                                            },
                                            '&:hover fieldset': {
                                                border: 'none',
                                            },
                                            '&.Mui-focused fieldset': {
                                                border: 'none',
                                            },
                                        },
                                        '& .MuiOutlinedInput-input': {
                                            padding: '12px 16px',
                                            fontSize: '16px',
                                            lineHeight: 1.5,
                                            color: '#1a1a1a',
                                            '&::placeholder': {
                                                color: '#9ca3af',
                                                opacity: 1,
                                            },
                                        },
                                    }}
                                />
                                <IconButton
                                    className="send-button"
                                    onClick={handleSend}
                                    disabled={!chatInput.trim() || videoFiles.length === 0 || isProcessing}
                                    sx={{
                                        width: 40,
                                        height: 40,
                                        backgroundColor: (chatInput.trim() && videoFiles.length > 0 && !isProcessing) ? '#4078F2' : '#d1d5db',
                                        '&:hover': {
                                            backgroundColor: (chatInput.trim() && videoFiles.length > 0 && !isProcessing) ? '#2d5bd9' : '#d1d5db',
                                        },
                                        '&.Mui-disabled': {
                                            backgroundColor: '#d1d5db',
                                        },
                                    }}
                                >
                                    <SendIcon sx={{fontSize: 20, color: 'white'}}/>
                                </IconButton>
                            </div>

                            {/* Helper text */}
                            <Typography
                                variant="caption"
                                sx={{
                                    color: '#FAFAFA',
                                    textAlign: 'center',
                                    marginTop: '1rem',
                                    flexShrink: 0,
                                }}
                            >
                                {videoFiles.length === 0 ?
                                    'Please upload at least one video first' :
                                    'Press Enter to send, Shift + Enter for new line'}
                            </Typography>
                        </div>
                    </div>
                )}

                {/* Main content wrapper that slides right */}
                <section
                    className={`relative overflow-hidden bg-white ${step >= 3 ? 'slide-right' : ''}`}
                    style={{
                        height: "100vh",
                        zIndex: 1,
                        borderRadius: step >= 3 ? '5rem' : '0',
                    }}
                >
                    {/* Decorative vector (blue river) - positioned and behind content */}
                    <div className="absolute pointer-events-none z-0"
                         style={{left: '-30vw', top: '-20vw', width: '139vw', transform: 'translateY(0) scale(1)'}}>
                        <img src={imgVector} alt="background vector" className="w-full h-auto object-cover"/>
                    </div>


                    <div className="relative" style={{
                        left: '4vw', top: '49vh',
                        animation: step > 0 ? 'slide-up 0.6s ease-in-out forwards' : 'none',
                        transition: 'transform 0.6s ease-in-out'
                    }}>
                        <Typography
                            variant="h1"
                            gutterBottom
                            sx={{
                                animation: step > 0 ? 'fade-out 0.5s ease-in-out forwards' : 'none',
                                transition: 'opacity 0.5s ease-in-out'
                            }}
                        >
                            Let&apos;s Get Started
                        </Typography>
                        <Button
                            component="label"
                            color="info"
                            role={undefined}
                            variant="contained"
                            tabIndex={-1}
                            startIcon={<CloudUploadIcon color="secondary" style={{fontSize: "3vh"}}/>}
                            sx={{
                                pl: "1.5vw",
                                pr: "1.5vw",
                                pb: "1.5vh",
                                pt: "1.5vh",
                            }}
                        >
                            <Typography variant="h5">Upload Videos</Typography>
                            <VisuallyHiddenInput
                                type="file"
                                accept="video/*"
                                onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
                                    const files = Array.from(event.target.files || []) as File[];
                                    console.log("Video files selected:", files);
                                    setVideoFiles(files);
                                    setStep(1);
                                }}
                                multiple
                            />
                        </Button>
                    </div>
                    <div
                        className="relative"
                        style={{
                            left: '4vw',
                            top: '36.5vh',
                            animation: step > 0 ? 'slide-in-field 0.6s ease-in-out forwards' : 'none',
                            opacity: step > 0 ? 1 : 0,
                            transition: 'opacity 0.6s ease-in-out'
                        }}
                    >
                        {step > 0 && <TextField
                            error
                            id="outlined-multiline-static"
                            label="Video Context"
                            multiline
                            rows={7}
                            onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
                                setVideoContext(event.target.value);
                                if (step < 2) {
                                    setStep(2);
                                }
                            }}
                            sx={{
                                minWidth: '22vw',
                                '& .MuiOutlinedInput-root': {
                                    '& textarea': {
                                        color: 'white',
                                        caretColor: 'white',
                                    },
                                },
                                '& .MuiOutlinedInput-input': {
                                    color: 'white',
                                    caretColor: 'white',
                                },
                                '& .MuiOutlinedInput-input::placeholder': {
                                    color: 'rgba(255, 255, 255, 0.7)',
                                    opacity: 1,
                                },
                            }}
                        />}
                    </div>

                    {windowSize.width > 0 && (
                        <svg
                            className="expand"
                            viewBox={"0 0 " + windowSize.width + " " + windowSize.height}
                            xmlns="http://www.w3.org/2000/svg"
                            style={{
                                position: 'fixed',
                                top: 0,
                                left: 0,
                                width: '100vw',
                                height: '100vh',
                                zIndex: step >= 3 ? 50 : -1,
                                pointerEvents: 'none',
                                opacity: step >= 3 ? 1 : 0,
                            }}
                        >
                            <circle
                                cx={windowSize.width * 0.65}
                                cy={windowSize.height * 0.68}
                                r="0"
                                className={step >= 3 ? "circle-expand" : ""}
                                fill="#4078F2"
                            />
                        </svg>
                    )}

                    <div className="absolute" style={{left: '59vw', top: '50vh'}}>
                        <div
                            key={`caption-${displayedStep}`}
                            className={isFadingOut ? 'fade-out-text' : 'fade-in-text-delayed'}
                        >
                            {infoCaptions[displayedStep]}
                        </div>
                        <div
                            key={`content-${displayedStep}`}
                            className={isFadingOut ? 'fade-out-text' : 'fade-in-text-delayed'}
                        >
                            {infoContent[displayedStep]}
                        </div>
                    </div>
                    {step > 0 && <img src={arrow} alt="arrow" className="absolute left-100 top-100" height="15vh"
                                      style={{animation: 'text-fade-in 0.9s ease-in-out forwards'}}/>}
                    {step > 1 && <div className={isFadingOut ? 'fade-no-fade-text' : 'fade-in-text-delayed'}
                                      style={{position: "absolute", left: '34vw', top: '35vh', opacity: "0"}}>
                        <Button
                            component="label"
                            color="info"
                            role={undefined}
                            variant="contained"
                            tabIndex={-1}
                            startIcon={<CloudUploadIcon color="secondary" style={{fontSize: "3vh"}}/>}
                            sx={{
                                pl: "1.5vw",
                                pr: "1.5vw",
                                pb: "1.5vh",
                                pt: "1.5vh",
                            }}
                        >
                            <Typography variant="h5">Add Audio</Typography>
                            <VisuallyHiddenInput
                                type="file"
                                accept="audio/*"
                                onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
                                    const files = event.target.files;
                                    if (files && files.length > 0) {
                                        console.log("Music file selected:", files[0]);
                                        setMusicFile(files[0]);
                                    }
                                    setStep(3);
                                }}
                            />
                        </Button>
                    </div>}
                    {step == 2 && <div className="absolute" style={{left: '59vw', top: '66vh'}}>
                        <div className={isFadingOut ? 'fade-no-fade-text' : 'fade-in-text-delayed'}
                             style={{opacity: "0%"}}>
                            <Button
                                component="label"
                                color="warning"
                                role={undefined}
                                variant="contained"
                                onClick={() => {
                                    setStep(3);
                                }}
                                tabIndex={-1}
                                startIcon={<CloudUploadIcon color="error" style={{fontSize: "3vh"}}/>}
                                sx={{
                                    pl: "1.5vw",
                                    pr: "1.5vw",
                                    pb: "1.5vh",
                                    pt: "1.5vh",
                                }}
                            >
                                <Typography variant="h6">No Audio</Typography>
                            </Button>
                        </div>
                    </div>}
                </section>
            </div>
            }

            {/* Anchor Logo - positioned at 3.5vw from left, 7vh from top */}
            <div className="absolute z-20" style={{left: '3vw', top: '5vh', width: '32vw'}}>
                <img src={imgAnchorLogo22} alt="Anchor logo" className="w-full h-auto object-contain"/>
            </div>
        </div>
    )
}
