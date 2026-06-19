"use client";

import React, { useState, useEffect, useRef } from "react";
import { 
  FileText, Upload, Send, MessageSquare, Award, 
  ChevronLeft, ChevronRight, ThumbsUp, ThumbsDown, BarChart2
} from "lucide-react";
import katex from "katex";
import "katex/dist/katex.min.css";

// Types
interface DocumentChoice {
  name: string;
  id: string;
}

interface ConceptNode {
  id: string;
  doc_id: string;
  label: string;
  explanation: string;
  page_number: number;
  memory: number;
  comprehension: number;
  structure: number;
  application: number;
}

interface Stats {
  documents_count: number;
  concepts_count: number;
  messages_count: number;
  evaluations_count: number;
}

interface VisualSpec {
  type: "plotly" | "katex" | "canvas" | "three";
  title: string;
  description: string;
  spec_json: {
    steps?: Array<{
      formula?: string;
      explanation?: string;
      title?: string;
      description?: string;
      details?: string;
    }>;
    data?: Array<{
      x: number[];
      y: number[];
      name?: string;
      line?: { color: string };
    }>;
    layout?: {
      xaxis?: { title?: string | { text?: string } };
      yaxis?: { title?: string | { text?: string } };
    };
  };
}

export default function WorkspacePage() {
  const [documents, setDocuments] = useState<DocumentChoice[]>([]);
  const [activeDocId, setActiveDocId] = useState<string>("");
  const [activePage, setActivePage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [pageText, setPageText] = useState<string>("");
  const [spottedConcepts, setSpottedConcepts] = useState<string[]>([]);
  
  const [selectedConceptId, setSelectedConceptId] = useState<string>("");
  const [conceptProfile, setConceptProfile] = useState<ConceptNode | null>(null);
  
  const [quizQuestion, setQuizQuestion] = useState<string>("");
  const [studentAnswer, setStudentAnswer] = useState<string>("");
  const [quizFeedback, setQuizFeedback] = useState<string>("");
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false);
  const [isGeneratingQuiz, setIsGeneratingQuiz] = useState<boolean>(false);
  
  const [visualSpec, setVisualSpec] = useState<VisualSpec | null>(null);
  
  const [chatHistory, setChatHistory] = useState<[string, string][]>([]);
  const [chatInput, setChatInput] = useState<string>("");
  const [chatStatus, setChatStatus] = useState<string>("Ready");
  const [isChatting, setIsChatting] = useState<boolean>(false);
  const [lastTraceId, setLastTraceId] = useState<string>("");
  const [feedbackStatus, setFeedbackStatus] = useState<string>("");
  
  const [customName, setCustomName] = useState<string>("");
  const [uploadStatus, setUploadStatus] = useState<string>("");
  const [stats, setStats] = useState<Stats>({
    documents_count: 0,
    concepts_count: 0,
    messages_count: 0,
    evaluations_count: 0
  });
  
  const [sessionUUID, setSessionUUID] = useState<string>("");
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Initialize Session ID
  useEffect(() => {
    setSessionUUID(crypto.randomUUID());
    loadStats();
    loadDocuments();
  }, []);

  // Poll stats and reload doc list
  const loadStats = async () => {
    try {
      const res = await fetch("/api/stats");
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const loadDocuments = async (selectId?: string) => {
    try {
      const res = await fetch("/api/documents");
      if (res.ok) {
        const data = await res.json();
        setDocuments(data);
        if (data.length > 0) {
          const nextActive = selectId || data[0].id;
          setActiveDocId(nextActive);
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Watch for Active Document Change
  useEffect(() => {
    if (!activeDocId) return;
    setActivePage(1);
    loadPageContent(activeDocId, 1);
    setSelectedConceptId("");
    setConceptProfile(null);
    setVisualSpec(null);
    setQuizQuestion("");
    setQuizFeedback("");
  }, [activeDocId]);

  // Load Page Text & Page Spotted Concepts
  const loadPageContent = async (docId: string, pageNum: number) => {
    try {
      const res = await fetch(`/api/documents/${docId}/pages/${pageNum}`);
      if (res.ok) {
        const data = await res.json();
        setPageText(data.text);
        setSpottedConcepts(data.concepts);
        setTotalPages(data.total_pages || 1);
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Listen to Window PostMessage from Graph IFrame
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (typeof event.data === "string" && event.data.includes("_concept_")) {
        setSelectedConceptId(event.data);
      }
    };
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, []);

  // Fetch Node Profile & Spec on Selection Change
  useEffect(() => {
    if (!selectedConceptId || !activeDocId) return;
    fetchConceptProfile(activeDocId, selectedConceptId);
    fetchVisualSpec(activeDocId, selectedConceptId);
    setQuizQuestion("");
    setQuizFeedback("");
    setStudentAnswer("");
  }, [selectedConceptId, activeDocId]);

  const fetchConceptProfile = async (docId: string, conceptId: string) => {
    try {
      const res = await fetch(`/api/documents/${docId}/concepts`);
      if (res.ok) {
        const data = await res.json();
        const found = data.nodes.find((n: ConceptNode) => n.id === conceptId);
        if (found) {
          setConceptProfile(found);
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchVisualSpec = async (docId: string, conceptId: string) => {
    try {
      const res = await fetch(`/api/documents/${docId}/visual-specs/${conceptId}`);
      if (res.ok) {
        const data = await res.json();
        setVisualSpec(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Handle PDF Upload
  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadStatus("Uploading & analyzing...");
    const formData = new FormData();
    formData.append("file", file);
    if (customName) {
      formData.append("custom_name", customName);
    }

    try {
      const res = await fetch("/api/documents/upload", {
        method: "POST",
        body: formData,
      });

      if (res.ok) {
        const data = await res.json();
        setUploadStatus(`Success! Ingested ${data.name}`);
        setCustomName("");
        await loadDocuments(data.doc_id);
        loadStats();
      } else {
        const err = await res.json();
        setUploadStatus(`Upload failed: ${err.detail || "Unknown error"}`);
      }
    } catch (err) {
      const error = err as Error;
      setUploadStatus(`Error: ${error.message}`);
    }
  };

  // Chat Send
  const handleSendChat = async () => {
    if (!chatInput.trim() || isChatting) return;
    setIsChatting(true);
    setFeedbackStatus("");
    
    const userMsg = chatInput;
    setChatInput("");
    setChatHistory(prev => [...prev, [userMsg, "Typing..."]]);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: userMsg,
          chat_history: chatHistory, // Send the real history (not sliced)
          doc_id: activeDocId,
          session_id: sessionUUID
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setChatHistory(prev => {
          const next = [...prev];
          next[next.length - 1] = [userMsg, data.response];
          return next;
        });
        setChatStatus(`Routed via ${data.route_taken.toUpperCase()} AGENT`);
        setLastTraceId(data.trace_id);
        loadStats();
      } else {
        const err = await res.json();
        setChatHistory(prev => {
          const next = [...prev];
          next[next.length - 1] = [userMsg, `Failed to generate reply: ${err.detail || "Server error"}`];
          return next;
        });
        setChatStatus("Failed to route");
      }
    } catch (e) {
      const error = e as Error;
      setChatHistory(prev => {
        const next = [...prev];
        next[next.length - 1] = [userMsg, `Error: ${error.message}`];
        return next;
      });
      setChatStatus("Network error");
    } finally {
      setIsChatting(false);
    }
  };

  // Feedback Up/Down
  const handleFeedback = async (rating: "up" | "down") => {
    if (!lastTraceId) return;
    try {
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating, trace_id: lastTraceId }),
      });
      if (res.ok) {
        setFeedbackStatus(rating === "up" ? "👍 Positive feedback logged" : "👎 Negative feedback logged");
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Quiz Generation
  const handleGenerateQuiz = async () => {
    if (!selectedConceptId || isGeneratingQuiz) return;
    setIsGeneratingQuiz(true);
    setQuizQuestion("Planning quiz question...");
    setQuizFeedback("");
    setStudentAnswer("");

    try {
      const res = await fetch("/api/evaluation/question", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ concept_id: selectedConceptId }),
      });
      if (res.ok) {
        const data = await res.json();
        setQuizQuestion(data.question);
      } else {
        setQuizQuestion("Failed to generate quiz question.");
      }
    } catch (e) {
      const error = e as Error;
      setQuizQuestion(`Error generating question: ${error.message}`);
    } finally {
      setIsGeneratingQuiz(false);
    }
  };

  // Quiz Submit
  const handleSubmitQuiz = async () => {
    if (!studentAnswer.trim() || isEvaluating) return;
    setIsEvaluating(true);

    try {
      const res = await fetch("/api/evaluation/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          concept_id: selectedConceptId,
          question: quizQuestion,
          answer: studentAnswer,
          doc_id: activeDocId
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setQuizFeedback(data.feedback_md);
        fetchConceptProfile(activeDocId, selectedConceptId);
        loadStats();
      } else {
        setQuizFeedback("Error submitting answer to the evaluation assessor.");
      }
    } catch (e) {
      const error = e as Error;
      setQuizFeedback(`Error submitting answer: ${error.message}`);
    } finally {
      setIsEvaluating(false);
    }
  };

  // Render LaTeX using KaTeX safely
  const renderFormula = (formula: string) => {
    try {
      const html = katex.renderToString(formula, { displayMode: true, throwOnError: false });
      return <div dangerouslySetInnerHTML={{ __html: html }} />;
    } catch {
      return <pre className="text-red-400">{formula}</pre>;
    }
  };

  // Calculated Unified Mastery Score Formula
  const calculateUnifiedScore = (c: ConceptNode) => {
    return Math.round(
      c.memory * 0.25 +
      c.comprehension * 0.30 +
      c.structure * 0.20 +
      c.application * 0.25
    );
  };

  const getMasteryColor = (score: number) => {
    if (score < 1) return "#b6b6ba"; // Grey
    if (score < 25) return "#7e9bc8"; // Blue
    if (score < 50) return "#8b78d9"; // Violet
    if (score < 75) return "#4fae84"; // Light green
    return "#16a06d"; // Deep emerald
  };

  interface Trace {
    x: number[];
    y: number[];
    name?: string;
    line?: { color: string };
  }

  interface PlotPoint {
    px: number;
    py: number;
    xVal: number;
    yVal: number;
  }

  interface PlotlySpecJSON {
    title?: string;
    description?: string;
    data?: Trace[];
    layout?: {
      xaxis?: { title?: string | { text?: string } };
      yaxis?: { title?: string | { text?: string } };
    };
  }

  // Inline SVG generator for Plotly specs fallback
  const renderPlotlySpec = (spec: PlotlySpecJSON) => {
    if (!spec || !spec.data) return null;
    const data = spec.data;
    const layout = spec.layout || {};

    return (
      <div className="w-full bg-slate-900 border border-slate-800 rounded-lg p-4 font-sans text-slate-300">
        <h4 className="font-semibold text-slate-100 mb-2">{spec.title || "Latencies Curve"}</h4>
        <p className="text-xs text-slate-400 mb-4">{spec.description}</p>
        
        {/* Simple SVG Graph Plotting */}
        <svg viewBox="0 0 500 250" className="w-full h-auto bg-slate-950 border border-slate-800 rounded-md">
          {/* Grid lines */}
          <line x1="50" y1="20" x2="50" y2="200" stroke="#334155" strokeWidth="2" />
          <line x1="50" y1="200" x2="480" y2="200" stroke="#334155" strokeWidth="2" />
          
          <line x1="50" y1="65" x2="480" y2="65" stroke="#1e293b" strokeDasharray="4" />
          <line x1="50" y1="110" x2="480" y2="110" stroke="#1e293b" strokeDasharray="4" />
          <line x1="50" y1="155" x2="480" y2="155" stroke="#1e293b" strokeDasharray="4" />
          
          {/* Traces */}
          {data.map((trace: Trace, tIdx: number) => {
            const xs = trace.x || [];
            const ys = trace.y || [];
            if (xs.length === 0) return null;
            
            const minX = Math.min(...xs);
            const maxX = Math.max(...xs);
            const maxY = Math.max(...ys, 50);
            
            const points = xs.map((xVal: number, idx: number) => {
              const yVal = ys[idx] || 0;
              const px = 50 + ((xVal - minX) / (maxX - minX || 1)) * 400;
              const py = 200 - (yVal / maxY) * 160;
              return { px, py, xVal, yVal };
            });
            
            const pathD = points.reduce((acc: string, p: PlotPoint, idx: number) => {
              return acc + `${idx === 0 ? "M" : "L"} ${p.px} ${p.py} `;
            }, "");
            
            const color = trace.line?.color || (tIdx === 0 ? "#4fae84" : "#8b78d9");
            
            return (
              <g key={tIdx}>
                {/* Line Path */}
                <path d={pathD} fill="none" stroke={color} strokeWidth="2.5" />
                {/* Points */}
                {points.map((p: PlotPoint, idx: number) => (
                  <circle 
                    key={idx} 
                    cx={p.px} 
                    cy={p.py} 
                    r="4" 
                    fill={color} 
                    className="hover:r-6 cursor-pointer"
                  >
                    <title>{`${trace.name || "Trace"}: x=${p.xVal}, y=${p.yVal}`}</title>
                  </circle>
                ))}
              </g>
            );
          })}
          
          {/* Axis Titles */}
          <text x="250" y="235" textAnchor="middle" fill="#64748b" className="text-[10px] font-medium">
            {typeof layout.xaxis?.title === "string" ? layout.xaxis.title : (layout.xaxis?.title?.text || "X Axis")}
          </text>
          <text x="15" y="110" textAnchor="middle" fill="#64748b" transform="rotate(-90 15 110)" className="text-[10px] font-medium">
            {typeof layout.yaxis?.title === "string" ? layout.yaxis.title : (layout.yaxis?.title?.text || "Y Axis")}
          </text>
        </svg>
        
        {/* Legends */}
        <div className="flex gap-4 justify-center mt-3">
          {data.map((trace: Trace, tIdx: number) => (
            <div key={tIdx} className="flex items-center gap-1 text-xs">
              <div 
                className="w-3 h-3 rounded-full" 
                style={{ backgroundColor: trace.line?.color || (tIdx === 0 ? "#4fae84" : "#8b78d9") }}
              />
              <span>{trace.name || `Trace ${tIdx + 1}`}</span>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const activeProfileScore = conceptProfile ? calculateUnifiedScore(conceptProfile) : 0;
  const activeProfileColor = conceptProfile ? getMasteryColor(activeProfileScore) : "#b6b6ba";

  return (
    <div className="min-h-screen bg-[#0b0f19] text-[#f8fafc] flex flex-col font-sans">
      {/* Header Panel */}
      <header className="px-6 py-4 bg-slate-900/60 backdrop-blur-md border-b border-white/5 flex flex-col md:flex-row justify-between items-start md:items-center gap-4 z-20">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-[#8b78d9] to-[#4fae84] bg-clip-text text-transparent">
            Paper Helper & Visual Study Companion
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Local-first multi-agent tutor & interactive study workspace (FastAPI & Langfuse Stack)
          </p>
        </div>
        
        {/* Stats Row */}
        <div className="flex flex-wrap gap-4 text-xs text-slate-400 bg-slate-950/65 border border-slate-800 rounded-lg p-2 px-4 shadow-inner">
          <div className="flex items-center gap-1.5 border-r border-slate-800 pr-3">
            <FileText size={14} className="text-[#8b78d9]" />
            <span>Documents: <strong className="text-slate-200">{stats.documents_count}</strong></span>
          </div>
          <div className="flex items-center gap-1.5 border-r border-slate-800 pr-3">
            <BarChart2 size={14} className="text-[#4fae84]" />
            <span>Concepts: <strong className="text-slate-200">{stats.concepts_count}</strong></span>
          </div>
          <div className="flex items-center gap-1.5 border-r border-slate-800 pr-3">
            <MessageSquare size={14} className="text-sky-400" />
            <span>Chats: <strong className="text-slate-200">{stats.messages_count}</strong></span>
          </div>
          <div className="flex items-center gap-1.5">
            <Award size={14} className="text-amber-500" />
            <span>Assessments: <strong className="text-slate-200">{stats.evaluations_count}</strong></span>
          </div>
        </div>
      </header>

      {/* Main Container Grid */}
      <main className="flex-1 p-6 grid grid-cols-1 lg:grid-cols-4 gap-6 overflow-hidden">
        
        {/* Left Column: workspace & page slider */}
        <section className="lg:col-span-1 flex flex-col gap-6">
          {/* Document select / Ingestion */}
          <div className="bg-slate-900/40 backdrop-blur border border-white/5 rounded-xl p-4 flex flex-col gap-4">
            <div>
              <h3 className="font-semibold text-sm text-slate-200 mb-2">Ingest New PDF</h3>
              <div className="flex flex-col gap-2">
                <input 
                  type="text" 
                  placeholder="Custom name (optional)" 
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  className="bg-slate-950 border border-slate-800 rounded-md p-1.5 px-3 text-xs w-full focus:outline-none focus:border-[#8b78d9]"
                />
                <button 
                  onClick={() => fileInputRef.current?.click()}
                  className="flex items-center justify-center gap-2 bg-slate-950 hover:bg-slate-900 border border-dashed border-slate-700 hover:border-slate-500 rounded-md p-2 text-xs text-slate-300 w-full transition"
                >
                  <Upload size={14} />
                  <span>Choose PDF & Ingest</span>
                </button>
                <input 
                  type="file" 
                  ref={fileInputRef} 
                  onChange={handleUpload} 
                  accept=".pdf" 
                  className="hidden" 
                />
                {uploadStatus && (
                  <p className="text-[10px] text-sky-400 mt-1 font-medium bg-sky-950/20 border border-sky-900/35 rounded p-1.5 text-center">
                    {uploadStatus}
                  </p>
                )}
              </div>
            </div>
            
            <div className="border-t border-slate-800 pt-3">
              <label className="font-semibold text-sm text-slate-200 block mb-2">Select Active Workspace</label>
              <select 
                value={activeDocId} 
                onChange={(e) => setActiveDocId(e.target.value)}
                className="bg-slate-950 border border-slate-800 rounded-md p-2 text-xs w-full text-slate-200 focus:outline-none focus:border-[#8b78d9]"
              >
                {documents.map((doc) => (
                  <option key={doc.id} value={doc.id}>{doc.name}</option>
                ))}
              </select>
            </div>
          </div>

          {/* PDF Pages content Slider panel */}
          <div className="bg-slate-900/40 backdrop-blur border border-white/5 rounded-xl p-4 flex-1 flex flex-col min-h-[300px]">
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-semibold text-sm text-slate-200">Extracted PDF Text</h3>
              {totalPages > 1 && (
                <div className="flex items-center gap-2 text-xs bg-slate-950 px-2 py-1 rounded border border-slate-800">
                  <button 
                    disabled={activePage === 1}
                    onClick={() => {
                      const prev = activePage - 1;
                      setActivePage(prev);
                      loadPageContent(activeDocId, prev);
                    }}
                    className="disabled:opacity-40 hover:text-slate-100"
                  >
                    <ChevronLeft size={14} />
                  </button>
                  <span className="font-medium text-slate-300">{activePage} / {totalPages}</span>
                  <button 
                    disabled={activePage === totalPages}
                    onClick={() => {
                      const next = activePage + 1;
                      setActivePage(next);
                      loadPageContent(activeDocId, next);
                    }}
                    className="disabled:opacity-40 hover:text-slate-100"
                  >
                    <ChevronRight size={14} />
                  </button>
                </div>
              )}
            </div>
            
            {/* Scrollable page text content */}
            <div className="flex-1 bg-slate-950/75 border border-slate-800 rounded-lg p-3 text-xs leading-relaxed overflow-y-auto max-h-[400px] text-slate-300 font-mono select-text whitespace-pre-wrap">
              {pageText || "*No document page content loaded.*"}
            </div>
            
            {/* Page Spotted Concepts pills */}
            <div className="mt-3 border-t border-slate-800 pt-3">
              <h4 className="font-medium text-xs text-slate-400 mb-2">Spotted Concepts (This Page):</h4>
              <div className="flex flex-wrap gap-1.5">
                {spottedConcepts.length > 0 ? (
                  spottedConcepts.map((cName, idx) => (
                    <span 
                      key={idx}
                      className="bg-[#8b78d9]/10 border border-[#8b78d9]/30 text-[#8b78d9] rounded-full px-2.5 py-0.5 text-[10px] font-medium"
                    >
                      {cName}
                    </span>
                  ))
                ) : (
                  <span className="text-[10px] text-slate-500 italic">No visual concepts spotted on this page.</span>
                )}
              </div>
            </div>
          </div>
        </section>

        {/* Middle Column: Interactive network graph & Visual Spec Sandboxes */}
        <section className="lg:col-span-2 flex flex-col gap-6 min-h-[500px]">
          {/* Vis.js network graph iframe card */}
          <div className="bg-slate-900/40 backdrop-blur border border-white/5 rounded-xl overflow-hidden flex flex-col h-[400px] relative">
            <div className="p-4 bg-slate-900/80 border-b border-white/5 flex justify-between items-center z-10">
              <h3 className="font-semibold text-sm text-slate-200">Interactive Study network graph</h3>
              <span className="text-[10px] text-slate-500">Nodes color-coded by mastery score level</span>
            </div>
            <div className="flex-1 bg-slate-950 relative">
              {activeDocId ? (
                <iframe 
                  src={`/api/documents/${activeDocId}/graph-html${selectedConceptId ? `?selected_id=${selectedConceptId}` : ""}`}
                  className="w-full h-full border-none"
                  title="Study Network Graph"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-slate-500 text-xs italic">
                  Select or upload a document workspace to view the concepts graph.
                </div>
              )}
            </div>
          </div>

          {/* Visual spec sandbox renderer */}
          <div className="bg-slate-900/40 backdrop-blur border border-white/5 rounded-xl p-4 flex-1 flex flex-col min-h-[250px]">
            <h3 className="font-semibold text-sm text-slate-200 mb-3">Visual Walkthrough Sandbox</h3>
            {visualSpec ? (
              <div className="flex-1 flex flex-col gap-3">
                <div className="flex justify-between items-center text-xs">
                  <span className="font-semibold text-slate-200">{visualSpec.title}</span>
                  <span className="bg-[#4fae84]/15 border border-[#4fae84]/35 text-[#4fae84] rounded px-2 py-0.5 font-medium uppercase text-[9px]">
                    {visualSpec.type}
                  </span>
                </div>
                
                {/* PlotlySpec */}
                {visualSpec.type === "plotly" && visualSpec.spec_json && (
                  <div className="flex-1 flex items-center justify-center">
                    {renderPlotlySpec(visualSpec.spec_json)}
                  </div>
                )}
                
                {/* Katex formulas step */}
                {visualSpec.type === "katex" && visualSpec.spec_json?.steps && (
                  <div className="flex-1 flex flex-col gap-4 overflow-y-auto p-2 bg-slate-950/50 border border-slate-800 rounded-md">
                    {visualSpec.spec_json.steps.map((step, sIdx: number) => (
                      <div key={sIdx} className="border-b border-slate-900 pb-3 last:border-0">
                        <div className="text-[10px] font-semibold text-slate-500 uppercase mb-1">Step {sIdx + 1}</div>
                        <div className="overflow-x-auto my-2 text-slate-100 flex justify-center">
                          {renderFormula(step.formula || "")}
                        </div>
                        <p className="text-xs text-slate-400 italic text-center mt-1">{step.explanation}</p>
                      </div>
                    ))}
                  </div>
                )}
                
                {/* Canvas visual pipeline steps */}
                {visualSpec.type === "canvas" && visualSpec.spec_json?.steps && (
                  <div className="flex-1 flex flex-col gap-3 overflow-y-auto max-h-[300px]">
                    <p className="text-xs text-slate-400 italic mb-2">{visualSpec.description}</p>
                    {visualSpec.spec_json.steps.map((step, sIdx: number) => (
                      <div key={sIdx} className="bg-slate-950/80 border border-slate-800 rounded-lg p-3 flex gap-3 items-start">
                        <div className="bg-[#8b78d9]/25 text-[#9e8be9] w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0">
                          {sIdx + 1}
                        </div>
                        <div>
                          <h4 className="text-xs font-semibold text-slate-200">{step.title}</h4>
                          <p className="text-[11px] text-slate-400 mt-1">{step.description}</p>
                          {step.details && (
                            <p className="text-[10px] text-slate-500 mt-1.5 bg-slate-900 p-1.5 rounded italic">
                              Details: {step.details}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Three.js 3D Visual Sandbox */}
                {visualSpec.type === "three" && (
                  <div className="flex-1 flex flex-col gap-2">
                    <p className="text-xs text-slate-400 italic">{visualSpec.description}</p>
                    <div className="flex-1 min-h-[350px] border border-slate-800 rounded-lg overflow-hidden relative bg-[#0b0f19]">
                      <iframe 
                        src={`/api/documents/${activeDocId}/visual-specs/${selectedConceptId}/three-html`}
                        className="w-full h-full border-none absolute inset-0"
                        title="3D Visual Sandbox"
                      />
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center text-slate-500 text-xs italic">
                Select a concept node in the study network graph above to generate and view its visual sandbox walkthrough.
              </div>
            )}
          </div>
        </section>

        {/* Right Column: Profile, Evaluator & Scoped Chat */}
        <section className="lg:col-span-1 flex flex-col gap-6 overflow-y-auto">
          {/* Concept Profile */}
          <div className="bg-slate-900/40 backdrop-blur border border-white/5 rounded-xl p-4 flex flex-col gap-3 shrink-0">
            <h3 className="font-semibold text-sm text-slate-200 border-b border-slate-800 pb-2">Concept Mastery Profile</h3>
            
            {conceptProfile ? (
              <div className="flex flex-col gap-4">
                <div>
                  <h4 className="font-bold text-slate-100 text-base">{conceptProfile.label}</h4>
                  <p className="text-xs text-slate-400 mt-1 leading-relaxed">{conceptProfile.explanation}</p>
                </div>
                
                {/* Unified score pill */}
                <div className="flex justify-between items-center bg-slate-950 border border-slate-800 rounded-lg p-3">
                  <span className="text-xs font-medium text-slate-400">Unified Mastery Score</span>
                  <span className="text-lg font-bold" style={{ color: activeProfileColor }}>
                    {activeProfileScore}%
                  </span>
                </div>
                
                {/* Score Axes */}
                <div className="flex flex-col gap-3">
                  <h5 className="text-[10px] font-semibold uppercase text-slate-500 tracking-wider">Mastery Axes</h5>
                  {[
                    { label: "Memory Recall", score: conceptProfile.memory, color: "#7e9bc8" },
                    { label: "Conceptual Comprehension", score: conceptProfile.comprehension, color: "#8b78d9" },
                    { label: "Structural Relationships", score: conceptProfile.structure, color: "#4fae84" },
                    { label: "Practical Application", score: conceptProfile.application, color: "#16a06d" }
                  ].map((axis, aIdx) => (
                    <div key={aIdx} className="text-xs">
                      <div className="flex justify-between font-medium mb-1">
                        <span className="text-slate-400 text-[11px]">{axis.label}</span>
                        <span className="text-slate-200">{axis.score}%</span>
                      </div>
                      <div className="w-full h-1.5 bg-slate-950 rounded-full overflow-hidden">
                        <div 
                          className="h-full rounded-full transition-all duration-500"
                          style={{ width: `${axis.score}%`, backgroundColor: axis.color }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-slate-500 text-xs italic text-center py-6">
                Click a concept node on the study graph to view its mastery profile.
              </p>
            )}
          </div>

          {/* Evaluator Panel */}
          {conceptProfile && (
            <div className="bg-slate-900/40 backdrop-blur border border-white/5 rounded-xl p-4 flex flex-col gap-3 shrink-0">
              <h3 className="font-semibold text-sm text-slate-200">Concept Mastery Evaluator Agent</h3>
              
              {!quizQuestion ? (
                <button 
                  onClick={handleGenerateQuiz}
                  disabled={isGeneratingQuiz}
                  className="w-full bg-slate-950 hover:bg-slate-900 border border-slate-800 text-xs font-semibold py-2 rounded-md transition disabled:opacity-40"
                >
                  {isGeneratingQuiz ? "Generating Question..." : "Start Mastery Assessment"}
                </button>
              ) : (
                <div className="flex flex-col gap-3 text-xs">
                  <div className="bg-slate-950/60 border border-slate-850 p-2.5 rounded text-slate-300">
                    <strong>Question:</strong> {quizQuestion}
                  </div>
                  
                  <textarea
                    rows={3}
                    placeholder="Type your explanation or mathematical answer here..."
                    value={studentAnswer}
                    onChange={(e) => setStudentAnswer(e.target.value)}
                    className="bg-slate-950 border border-slate-800 rounded-md p-2 text-xs focus:outline-none focus:border-[#8b78d9] w-full text-slate-200 resize-none"
                  />
                  
                  <div className="flex gap-2">
                    <button 
                      onClick={() => setQuizQuestion("")}
                      className="bg-slate-950 hover:bg-slate-900 border border-slate-800 text-[10px] py-1.5 px-3 rounded transition font-medium"
                    >
                      Cancel
                    </button>
                    <button 
                      onClick={handleSubmitQuiz}
                      disabled={!studentAnswer.trim() || isEvaluating}
                      className="flex-1 bg-[#8b78d9] hover:bg-[#7a67cb] text-slate-950 font-bold py-1.5 rounded transition text-[11px] disabled:opacity-40"
                    >
                      {isEvaluating ? "Evaluating..." : "Submit Answer"}
                    </button>
                  </div>
                  
                  {quizFeedback && (
                    <div className="mt-2 bg-[#16a06d]/10 border border-[#16a06d]/20 rounded p-2.5 text-[11px] text-slate-300 max-h-[200px] overflow-y-auto leading-relaxed select-text whitespace-pre-wrap">
                      {quizFeedback}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Scoped Chat Panel */}
          <div className="bg-slate-900/40 backdrop-blur border border-white/5 rounded-xl p-4 flex-1 flex flex-col min-h-[300px] max-h-[450px]">
            <h3 className="font-semibold text-sm text-slate-200 mb-2">Scoped Chat Assistant</h3>
            
            {/* Messages box */}
            <div className="flex-1 bg-slate-950/75 border border-slate-800 rounded-lg p-3 overflow-y-auto flex flex-col gap-3 min-h-[150px]">
              {chatHistory.length > 0 ? (
                chatHistory.map((msg, idx) => (
                  <div key={idx} className="flex flex-col gap-1">
                    {/* User */}
                    <div className="bg-slate-900 p-2 rounded-lg max-w-[85%] self-start text-xs border border-slate-800">
                      <div className="text-[9px] font-semibold text-slate-500 uppercase mb-0.5">Student</div>
                      <div className="text-slate-300 font-medium select-text">{msg[0]}</div>
                    </div>
                    {/* AI */}
                    <div className="bg-[#8b78d9]/10 p-2 rounded-lg max-w-[85%] self-end text-xs border border-[#8b78d9]/20">
                      <div className="text-[9px] font-semibold text-[#8b78d9] uppercase mb-0.5">Assistant</div>
                      <div className="text-slate-200 select-text leading-relaxed whitespace-pre-wrap">{msg[1]}</div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="my-auto text-center text-slate-500 text-xs italic">
                  Ask a question about the document text or company policies here.
                </div>
              )}
            </div>
            
            {/* Input Row */}
            <div className="mt-3 flex flex-col gap-2">
              <div className="flex gap-2">
                <input 
                  type="text"
                  placeholder="Ask a question..."
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSendChat()}
                  className="bg-slate-950 border border-slate-800 rounded-md p-2 text-xs focus:outline-none focus:border-[#8b78d9] flex-1 text-slate-200"
                />
                <button 
                  onClick={handleSendChat}
                  disabled={!chatInput.trim() || isChatting}
                  className="bg-[#8b78d9] hover:bg-[#7a67cb] text-slate-950 p-2 rounded-md transition shrink-0 disabled:opacity-40"
                >
                  <Send size={14} />
                </button>
              </div>
              
              <div className="flex justify-between items-center text-[10px] text-slate-500">
                <span className="italic">{chatStatus}</span>
                {lastTraceId && (
                  <div className="flex gap-1.5 items-center">
                    <span>Helpful?</span>
                    <button onClick={() => handleFeedback("up")} className="hover:text-[#4fae84]"><ThumbsUp size={11} /></button>
                    <button onClick={() => handleFeedback("down")} className="hover:text-red-400"><ThumbsDown size={11} /></button>
                  </div>
                )}
              </div>
              {feedbackStatus && (
                <p className="text-[9px] text-sky-400 text-center font-semibold bg-sky-950/15 p-1 rounded">
                  {feedbackStatus}
                </p>
              )}
            </div>
          </div>
        </section>

      </main>
    </div>
  );
}
