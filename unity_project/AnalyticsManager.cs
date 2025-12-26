using UnityEngine;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using System.IO;

public class AnalyticsManager : MonoBehaviour
{
    public static AnalyticsManager Instance;
    
    [Header("Configuration")]
    public string serverURL = "http://localhost:5000";
    public bool enableAnalytics = true;
    
    [Header("Session Info")]
    public string sessionId;
    public string visitorId;
    public float sessionStartTime;
    public int queriesMade = 0;
    public int artworksViewed = 0;
    
    private string currentQueryId;
    private Dictionary<string, float> artworkViewTimes = new Dictionary<string, float>();
    
    void Awake()
    {
        if (Instance == null)
        {
            Instance = this;
            DontDestroyOnLoad(gameObject);
            InitializeAnalytics();
        }
        else
        {
            Destroy(gameObject);
        }
    }
    
    void InitializeAnalytics()
    {
        if (!enableAnalytics) return;
        
        // Generate or load visitor ID
        visitorId = PlayerPrefs.GetString("art_gallery_visitor_id", "");
        if (string.IsNullOrEmpty(visitorId))
        {
            visitorId = System.Guid.NewGuid().ToString().Substring(0, 8);
            PlayerPrefs.SetString("art_gallery_visitor_id", visitorId);
            PlayerPrefs.Save();
        }
        
        // Generate session ID
        sessionId = System.Guid.NewGuid().ToString();
        sessionStartTime = Time.time;
        
        Debug.Log($"📊 Analytics initialized - Visitor: {visitorId}, Session: {sessionId}");
    }
    
    void OnApplicationQuit()
    {
        if (!enableAnalytics) return;
        
        SaveSessionSummary();
    }
    
    public void StartQuery(string queryText)
    {
        if (!enableAnalytics) return;
        
        queriesMade++;
        currentQueryId = System.Guid.NewGuid().ToString();
        
        Debug.Log($"📊 Query started: {queryText.Substring(0, Mathf.Min(30, queryText.Length))}...");
    }
    
    public void RecordQueryResponse(string queryId, string response, List<ArtworkData> artworks)
    {
        if (!enableAnalytics) return;
        
        currentQueryId = queryId;
        
        // Could save locally or send to server
        QueryResponseData data = new QueryResponseData
        {
            queryId = queryId,
            sessionId = sessionId,
            visitorId = visitorId,
            response = response,
            artworks = artworks,
            timestamp = Time.time
        };
        
        SaveQueryResponse(data);
    }
    
    public void StartViewingArtwork(string artworkId, string title, string artist)
    {
        if (!enableAnalytics) return;
        
        if (!artworkViewTimes.ContainsKey(artworkId))
        {
            artworkViewTimes[artworkId] = Time.time;
        }
    }
    
    public void StopViewingArtwork(string artworkId, string title, string artist)
    {
        if (!enableAnalytics || !artworkViewTimes.ContainsKey(artworkId)) return;
        
        float startTime = artworkViewTimes[artworkId];
        float duration = Time.time - startTime;
        
        artworksViewed++;
        
        // Send to server
        StartCoroutine(SendArtworkClickToServer(currentQueryId, artworkId, duration));
        
        // Save locally
        ArtworkViewData viewData = new ArtworkViewData
        {
            artworkId = artworkId,
            artworkTitle = title,
            artist = artist,
            viewDuration = duration,
            timestamp = Time.time,
            queryId = currentQueryId
        };
        
        SaveArtworkView(viewData);
        
        artworkViewTimes.Remove(artworkId);
        
        Debug.Log($"📊 Artwork viewed: {title} ({duration:F1}s)");
    }
    
    IEnumerator SendArtworkClickToServer(string queryId, string artworkId, float duration)
    {
        if (string.IsNullOrEmpty(queryId)) yield break;
        
        WWWForm form = new WWWForm();
        form.AddField("query_id", queryId);
        form.AddField("artwork_id", artworkId);
        form.AddField("duration", duration.ToString("F2"));
        
        using (UnityWebRequest www = UnityWebRequest.Post(
            serverURL + "/api/analytics/record-click", form))
        {
            yield return www.SendWebRequest();
            
            if (www.result == UnityWebRequest.Result.Success)
            {
                Debug.Log("📊 Artwork click recorded");
            }
        }
    }
    
    public void SubmitFeedback(int score, string comment = "")
    {
        if (!enableAnalytics || string.IsNullOrEmpty(currentQueryId)) return;
        
        StartCoroutine(SendFeedbackToServer(currentQueryId, score, comment));
        
        FeedbackData feedback = new FeedbackData
        {
            feedbackId = System.Guid.NewGuid().ToString(),
            queryId = currentQueryId,
            score = score,
            comment = comment,
            timestamp = Time.time
        };
        
        SaveFeedback(feedback);
    }
    
    IEnumerator SendFeedbackToServer(string queryId, int score, string comment)
    {
        WWWForm form = new WWWForm();
        form.AddField("query_id", queryId);
        form.AddField("score", score.ToString());
        form.AddField("comment", comment);
        
        using (UnityWebRequest www = UnityWebRequest.Post(
            serverURL + "/api/analytics/feedback", form))
        {
            yield return www.SendWebRequest();
            
            if (www.result == UnityWebRequest.Result.Success)
            {
                Debug.Log("📊 Feedback submitted");
            }
        }
    }
    
    public void GetTopArtworks(System.Action<List<ArtworkAnalytics>> callback)
    {
        StartCoroutine(FetchTopArtworks(callback));
    }
    
    IEnumerator FetchTopArtworks(System.Action<List<ArtworkAnalytics>> callback)
    {
        string url = serverURL + "/api/analytics/top-artworks?limit=10";
        
        using (UnityWebRequest www = UnityWebRequest.Get(url))
        {
            yield return www.SendWebRequest();
            
            if (www.result == UnityWebRequest.Result.Success)
            {
                string jsonResponse = www.downloadHandler.text;
                AnalyticsResponse response = JsonUtility.FromJson<AnalyticsResponse>(jsonResponse);
                
                callback?.Invoke(response.artworks);
            }
            else
            {
                Debug.LogError($"📊 Failed to fetch top artworks: {www.error}");
                callback?.Invoke(new List<ArtworkAnalytics>());
            }
        }
    }
    
    void SaveSessionSummary()
    {
        float sessionDuration = Time.time - sessionStartTime;
        
        SessionSummary summary = new SessionSummary
        {
            sessionId = sessionId,
            visitorId = visitorId,
            startTime = sessionStartTime,
            duration = sessionDuration,
            queriesMade = queriesMade,
            artworksViewed = artworksViewed,
            timestamp = Time.time
        };
        
        string json = JsonUtility.ToJson(summary, true);
        string filePath = Path.Combine(Application.persistentDataPath, $"session_{sessionId}.json");
        File.WriteAllText(filePath, json);
        
        Debug.Log($"📊 Session saved: {filePath}");
    }
    
    void SaveQueryResponse(QueryResponseData data)
    {
        string dir = Path.Combine(Application.persistentDataPath, "analytics", "queries");
        Directory.CreateDirectory(dir);
        
        string json = JsonUtility.ToJson(data, true);
        File.WriteAllText(Path.Combine(dir, $"{data.queryId}.json"), json);
    }
    
    void SaveArtworkView(ArtworkViewData data)
    {
        string dir = Path.Combine(Application.persistentDataPath, "analytics", "views");
        Directory.CreateDirectory(dir);
        
        string json = JsonUtility.ToJson(data, true);
        File.WriteAllText(Path.Combine(dir, $"{data.artworkId}_{Time.time}.json"), json);
    }
    
    void SaveFeedback(FeedbackData data)
    {
        string dir = Path.Combine(Application.persistentDataPath, "analytics", "feedback");
        Directory.CreateDirectory(dir);
        
        string json = JsonUtility.ToJson(data, true);
        File.WriteAllText(Path.Combine(dir, $"{data.feedbackId}.json"), json);
    }
    
    // Data Structures
    [System.Serializable]
    public class ArtworkData
    {
        public string id;
        public string title;
        public string artist;
        public float similarity;
    }
    
    [System.Serializable]
    public class QueryResponseData
    {
        public string queryId;
        public string sessionId;
        public string visitorId;
        public string response;
        public List<ArtworkData> artworks;
        public float timestamp;
    }
    
    [System.Serializable]
    public class ArtworkViewData
    {
        public string artworkId;
        public string artworkTitle;
        public string artist;
        public float viewDuration;
        public float timestamp;
        public string queryId;
    }
    
    [System.Serializable]
    public class FeedbackData
    {
        public string feedbackId;
        public string queryId;
        public int score;
        public string comment;
        public float timestamp;
    }
    
    [System.Serializable]
    public class SessionSummary
    {
        public string sessionId;
        public string visitorId;
        public float startTime;
        public float duration;
        public int queriesMade;
        public int artworksViewed;
        public float timestamp;
    }
    
    [System.Serializable]
    public class ArtworkAnalytics
    {
        public int artwork_id;
        public string artwork_title;
        public string artwork_artist;
        public float demand_score;
        public int total_queries;
        public int total_clicks;
    }
    
    [System.Serializable]
    public class AnalyticsResponse
    {
        public List<ArtworkAnalytics> artworks;
    }
}
