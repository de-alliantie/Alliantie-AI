import {
  Streamlit,
  withStreamlitConnection,
  ComponentProps,
} from "streamlit-component-lib"
import React, {
  useCallback,
  useEffect,
  useMemo,
  useState,
  ReactElement,
} from "react"

/**
 * A template for creating Streamlit components with React
 *
 * This component demonstrates the essential structure and patterns for
 * creating interactive Streamlit components, including:
 * - Accessing props and args sent from Python
 * - Managing component state with React hooks
 * - Communicating back to Streamlit via Streamlit.setComponentValue()
 * - Using the Streamlit theme for styling
 * - Setting frame height for proper rendering
 *
 * @param {ComponentProps} props - The props object passed from Streamlit
 * @param {Object} props.args - Custom arguments passed from the Python side
 * @param {string} props.args.name - Example argument showing how to access Python-defined values
 * @param {string} props.args.sas_urls - Example argument showing how to access Python-defined values
 * @param {boolean} props.disabled - Whether the component is in a disabled state 
 * @param {Object} props.theme - Streamlit theme object for consistent styling
 * @returns {ReactElement} The rendered component
 */
function MyComponent({ args, disabled, theme }: ComponentProps): ReactElement {
  // Extract custom arguments passed from Python
  const sasUrls = args["sas_urls"]
  const enableUpload = args["enable_upload"]
  const [disableChooseFiles, setDisableChooseFiles] = useState(false)
  // Component state
  const [isFocused, setIsFocused] = useState(false)
  const [droppedFiles, setDroppedFiles] = useState<File[]>([])
  const [uploadProgress, setUploadProgress] = useState<number[]>([])

  // Function to be triggered when any relevant prop or state changes
  const onComponentChange = useCallback(() => {
    // You can add any logic here that should run when the component changes
    // For demonstration, we'll just log the current state and props
    console.log("Component changed:", {
      args,
      disabled,
      theme,
      droppedFiles,
      uploadProgress
    });
    // You can also send updates to Streamlit or perform other actions here
  }, [args, disabled, theme, droppedFiles, uploadProgress]);

  // useEffect to trigger onComponentChange when any dependency changes
  useEffect(() => {
    onComponentChange();
  }, [onComponentChange]);

  /**
   * Dynamic styling based on Streamlit theme and component state
   * This demonstrates how to use the Streamlit theme for consistent styling
   */
  const style: React.CSSProperties = useMemo(() => {
    if (!theme) return {}

    // Use the theme object to style the button border
    // Access theme properties like primaryColor, backgroundColor, etc.
    const borderStyling = `1px solid ${isFocused ? theme.primaryColor : "gray"}`
    return { border: borderStyling, outline: borderStyling }
  }, [theme, isFocused])

  // Ensure Streamlit resizes the component when files or progress change
  useEffect(() => {
    Streamlit.setFrameHeight();
  }, [droppedFiles, uploadProgress])

  /**
   * Focus handler for the button
   * Updates visual state when the button receives focus
   */
  const onFocus = useCallback((): void => {
    setIsFocused(true)
  }, [])

  /**
   * Blur handler for the button
   * Updates visual state when the button loses focus
   */
  const onBlur = useCallback((): void => {
    setIsFocused(false)
  }, [])

  // Upload files to provided SAS URLs
  const uploadFiles = async (sasUrls: string[]) => {
    setDisableChooseFiles(true);
    const progressArr = Array(droppedFiles.length).fill(0)
    setUploadProgress(progressArr)
    const fileNames = droppedFiles.map(file => file.name);
    console.log({ filenames: fileNames, uploadPressed: true, uploadCompleted: false });
    Streamlit.setComponentValue({ filenames: fileNames, uploadPressed: true, uploadCompleted: false });
    for (let i = 0; i < droppedFiles.length; i++) {
      const file = droppedFiles[i];
      const uploadUrl = sasUrls[i];
      console.log(`Uploading file #${i + 1}:`, file.name, "→", uploadUrl);

      // upload progress bar
      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("PUT", uploadUrl, true);
        xhr.setRequestHeader("x-ms-blob-type", "BlockBlob");
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            const percent = Math.round((event.loaded / event.total) * 100);
            setUploadProgress(prev => {
              const updated = [...prev];
              updated[i] = percent;
              return updated;
            });
          }
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve();
          } else {
            alert(`❌ Upload gefaald voor ${file.name}`);
            reject();
          }
        };
        xhr.onerror = () => {
          alert(`❌ Error tijdens uploaden van ${file.name}`);
          reject();
        };
        xhr.send(file);
      });
    }
    // Send filenames and uploadPressed=true to Streamlit
    console.log({ filenames: fileNames, uploadPressed: true, uploadCompleted: true });
    Streamlit.setComponentValue({ filenames: fileNames, uploadPressed: true, uploadCompleted: true });
  };

  // Handle file input change event
  const fileInputChangeHandler = (ev: React.ChangeEvent<HTMLInputElement>) => {
    const files = ev.target.files ? Array.from(ev.target.files) : [];
    setDroppedFiles(files);
    const fileNames = files.map(file => file.name);

    // Send filenames and uploadPressed=false to Streamlit
    Streamlit.setComponentValue({ filenames: fileNames, uploadPressed: false, uploadCompleted: false });
    console.log({ filenames: fileNames, uploadPressed: false, uploadCompleted: false});
  };

  return (
    <div
      style={{ border: "2px dashed #aaa", padding: 20, textAlign: "center" }}
      // onDrop={dropHandler}
      // onDragOver={dragOverHandler}
    >
      <label
        htmlFor="fileInput"
        className={`btn btn-light`}
        hidden={disableChooseFiles}
      >
        {disableChooseFiles ? 'Choose Files' : 'Selecteer bestanden'}
        <input
          type="file"
          id="fileInput"
          multiple
          onChange={fileInputChangeHandler}
          style={{ display: 'none' }}
        />
      </label>
      <br></br>
      <button
        onClick={() => uploadFiles(sasUrls)}
        disabled={!enableUpload}
        hidden={!enableUpload}
        className={`btn btn-primary`}
        // style={{ minWidth: 120, fontWeight: 600, fontSize: 15 }}
      >
        Upload
      </button>
      <div style={{marginTop: 20}}>
        {droppedFiles.map((file, idx) => (
          <div key={file.name} style={{marginBottom: 8}}>
            <span>📄 {file.name}</span>
            <div style={{ width: '100%', background: '#eee', height: 8, borderRadius: 4, marginTop: 2 }}>
              <div style={{ width: `${uploadProgress[idx] || 0}%`, background: '#4caf50', height: '100%', borderRadius: 4 }}></div>
            </div>
            <span style={{ fontSize: 12 }}>{uploadProgress[idx] ? `${uploadProgress[idx]}%` : ''}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * withStreamlitConnection is a higher-order component (HOC) that:
 * 1. Establishes communication between this component and Streamlit
 * 2. Passes Streamlit's theme settings to your component
 * 3. Handles passing arguments from Python to your component
 * 4. Handles component re-renders when Python args change
 *
 * You don't need to modify this wrapper unless you need custom connection behavior.
 */
export default withStreamlitConnection(MyComponent)
