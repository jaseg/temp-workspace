using System.Collections;
using UnityEngine;

namespace BeatSaverVoting
{
    public class CoroutineWithData {
        public Coroutine Coroutine { get; }
        public object result;
        private readonly IEnumerator _target;
        public CoroutineWithData(MonoBehaviour owner, IEnumerator target) {
            _target = target;
            Coroutine = owner.StartCoroutine(Run());
        }

        private IEnumerator Run() {
            while(_target.MoveNext()) {
                result = _target.Current;
                yield return result;
            }
        }
    }
}